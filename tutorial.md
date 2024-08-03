---
title: "Ephemeral Environments with Pulumi Automation API"
author: Adam Gordon Bell
---

# Ephemeral Environments with Pulumi Automation API

> An ephemeral environment is a short-lived, isolated deployment of an application and its supporting infrastructure. Ephemeral environments provide robust, on-demand platforms for running tests, previewing features, and collaborating asynchronously across teams.

For me, ephemeral environments have always been the holy grail of software development. Imagine working on a service that needs to talk to S3, send messages to a Kafka cluster, be fronted by an API gateway, and be called by a frontend JS app. Interacting on this locally and testing that nothing has broken at the service boundaries becomes a big challenge.

I want a way to quickly test my changes end to end, but all solutions to that have always left me wanting. I could point everything to a staging environment, which is a real pain for Kafka messages. I could try to run everything locally or make sure I have integration tests that test across service boundaries and depend on a slow CI/CD cycle to catch any issues. 

But if I could spin a copy of the whole world from scratch, from my branch – an environemtn that just contained my changes – and then destroy it at the end, I would be so happy.

Thankfully, doing this with Pulumi and the Pulumi automation API is possible. If all the infrastructure and services are described as a Pulumi program, I can automatically set up and tear down an environment. Then, if I use the Pulumi automation API, I can have a script in my language of choice in my repo that sets and tears down an ephemeral version of my environment as needed.

So, let's give it a shot! I will keep the scope small, so this is more of a tutorial than a book. But don't worry - I'll still show you how to start up and tear down epithermal environments programmatically using Python.

## My App: A Simple Fibonacci Service

The app I'll use to demonstrate this is a simple Fibonacci service that returns the value of the nth Fibonacci service, written in Python and Flask:

```Python
from flask import Flask, jsonify, Response
from functools import lru_cache
from typing import Tuple

app = Flask(__name__)

@lru_cache(maxsize=None)
def fib(n: int) -> int:
    if n < 2:
        return n
    return fib(n-1) + fib(n-2)

@app.route('/fib/<int:n>')
def get_fib(n: int) -> Tuple[Response, int]:
    if n < 0:
        return jsonify({"error": "Please provide a non-negative integer"}), 400
    result = fib(n)
    return jsonify({"n": n, "fib": result}), 200

@app.route('/health')
def health_check() -> Tuple[Response, int]:
    return jsonify({"status": "healthy"}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
```

I test this out locally by starting it up in a docker container:

```
> docker build -t fibhatchery .
> docker run -d -p 8080:8080 fibhatchery
> curl 0.0.0.0:8080/fib/20
{"fib":6765,"n":20}
```

A setup as simple as this may not warrant ephemeral environments for development since it is so easy to start. Still, it could be helpful for PR, where a CI job could start up an ephemeral version of your stack for reviewers to poke at and review.

To that end, our goal is a Python program to deploy this service to AWS so that we can curl against it.

## The Pulumi Program

The service will be run by building and pushing an image to my existing ECR repo and then starting up an AWS AppRun service for this image.

In my `fibfactor.py` file, I must create a pulumi program that starts everything up. 

```Python
def pulumi_program() -> None:

```

This program will take my ephemeral environment's name and its port as input:

```python
    config = pulumi.Config()
    app_name = config.require("appName")
    container_port = config.require_int("containerPort")
```

It will also run in `us-west-2`:

```Python
    region = "us-west-2"
    aws_provider = aws.Provider("aws-provider", region=region)
```

I then build the image using the [docker build](https://www.pulumi.com/registry/packages/docker-build/) package, tagging my image with the passed-in app name:

```Python
    image = docker.Image("app-image",
        build=docker.DockerBuildArgs(
            context=".",
            platform="Linux/amd64"
        ),
        image_name=f"public.ecr.aws/o2l3o3x9/adamgordonbell:{app_name}",
        registry=docker.RegistryArgs(
            server="public.ecr.aws"
        ),
        opts=pulumi.ResourceOptions(provider=aws_provider)
    )

```

Then, once I've done that, I create my [App Runner](https://www.pulumi.com/registry/packages/aws/api-docs/apprunner/service/) service:

```Python
    app_runner_service = aws.apprunner.Service("app-runner-service",
        service_name=f"{app_name}-service",
        source_configuration=aws.apprunner.ServiceSourceConfigurationArgs(
            auto_deployments_enabled=False,
            image_repository=aws.apprunner.ServiceSourceConfigurationImageRepositoryArgs(
                image_configuration=aws.apprunner.ServiceSourceConfigurationImageRepositoryImageConfigurationArgs(
                    port=str(container_port)
                ),
                image_identifier=image.image_name,
                image_repository_type="ECR_PUBLIC"
            )
        ),
        instance_configuration=aws.apprunner.ServiceInstanceConfigurationArgs(
            cpu="1024",
            memory="2048"
        ),
        opts=pulumi.ResourceOptions(provider=aws_provider)
    )
```

I'm using my existing public ECR repo for simplicity, as the tag name will keep each ephemeral environment separate. Then, all I need to do is make sure my program exports the service URL, and I should be set.

```
    pulumi.export("app_runner_service_url", app_runner_service.service_url)
```

Now, let's start hooking this up with automation.

## Automation API:

For today's purposes, I will make things a bit more manual. You will create an environment like this:

```
python fibfactory.py --env-id test1 create
```
And that will create our ephemeral environment, which is in Pulumi terms stack named `fib-factory-test1`. I'll also add the ability to list all ephemeral environments for this repo and destroy them by name.


### Create environment

Our slightly simplified create looks like this. We import the automation module, create our stack name, and then our stack:

```
from pulumi import automation as auto

PROJECT_NAME = "fibfactory"
def create_env(env_id: str) -> None:

    stack_name = f"{PROJECT_NAME}-{env_id}"
    
    stack = auto.create_or_select_stack(stack_name=stack_name,
                                            project_name=PROJECT_NAME,
                                            program=pulumi_program)

```

An important detail is `program=pulumi_program.` `pulumi_program` is our function above that builds our environment. We pass it to our stack, and, spoiler alert, it will be executed when we call `stack.up`.

Next, we pass in our required parameters, which we set up at the beginning of this process.

```
stack.set_config("appName", auto.ConfigValue(value=f"fib-app-{env_id}"))
stack.set_config("containerPort", auto.ConfigValue(value="8080"))
```

And then we start up the stack and get the service name out of it:


```
        up_res = stack.up()
        
        service_url = up_res.outputs.get('app_runner_service_url', {}).value
```

The final version of this code, in GitHub, has some logging and error-catching flourishes, but that is the code logic.

Let's try it.

```
> python fibfactory.py --env-id test1 create
Successfully initialized stack fibfactory-test1
Config set
 Deploying the stack...
 ...
 ...
Updating (fibfactory-test1)
View Live: https://app.pulumi.com/adamgordonbell/fibfactory/fibfactory-test1/updates/1
Stack fibfactory-test1 created successfully
Service URL: jdamju6gpd.us-west-2.awsapprunner.com
```

Calling:

```
> curl https://jdamju6gpd.us-west-2.awsapprunner.com/fib/20
{"fib":6765,"n":20}
```

It works!!

Ok, let's do the promised `list` and `destroy`.

## List and Destroy

For listing the existing environments, we can use the informatively named `list_stacks.`

``` Python
def list_envs() -> None:
    workspace = auto.LocalWorkspace(project_settings=auto.ProjectSettings(name=PROJECT_NAME, runtime="python"))
    stacks = workspace.list_stacks()
```

We can filter these out by our project prefix and get just the ones we've created with this script:

```Python
 print("Active environments:")
        for stack in stacks:
            if stack.name.starts with(PROJECT_NAME):
                print(f"- {stack.name}")
        if not any(stack.name.startswith(PROJECT_NAME) for stack in stacks):
            print("No active environments found.")
```

Looks like this, in operation:

```
> Python fibfactory.py list                                
Active environments:
- fibfactory-test1
```

For destroy, we repeat create's `select_stack`:

```
def destroy_env(env_id: str) -> None:
    stack_name = f"{PROJECT_NAME}-{env_id}"
    
    stack = auto.select_stack(stack_name=stack_name,
                                  project_name=PROJECT_NAME,
                                  program=pulumi_program)

```

But now, instead of `up`, we call `destroy` and then `remove_stack`:

```        
        destroy_result = stack.destroy()
        stack.workspace.remove_stack(stack_name)

```

The full version has some logging and error checking, but the end result is this:

```
> python fibfactory.py --env-id test1 destroy 
Destroying stack fibfactory-test1
Destroying (fibfactory-test1)

View Live: https://app.pulumi.com/adamgordonbell/fibfactory/fibfactory-test1/updates/2
...

The resources in the stack have been deleted, but the history and configuration associated with the stack are still maintained.

Resources destroyed: {'delete': 4}

Stack fibfactory-test1 destroyed successfully
Stack fibfactory-test1 removed completely
```

## Benefits

So, all this is super cool, right? Just think of what we can build with this automation API. I mentioned PR reviews earlier; since we can programmatically list, start up, and tear down environments, it would be easy to incorporate this into the CI/CD process and the PR review workflow. A Github action sets up an ephemeral environment of your full infrastructure stack and services, keeps it up to date, and then tears it down on merge. That would be powerful. 

I've gotten very used to the way Netlify and Vercel spin up an ephemeral front end for each PR; now, we can extend it to the entire stack and all our infrastructure. Granted, this specific example of a stand-alone Python flask app being deployed ad-hoc is pretty minor, but the implied potential is enormous. 

And the benefits don't just stop at ease-of-use. How much time has been spent chasing down inconsistencies in some persistent staging or preproduction environment? How many valuable integration tests are a maintenance nightmare because of environment drift or inconsistent data left behind by failure? 

Programmatically created and destroyed ephemeral environments are work to set up, but then—you get consistency; you get isolation; you can collaborate by sharing a link to your whole stack for a coworker to test; you can tear them down when not in use; you get faster feedback loops; and you can scale your environments as you scale your team. 

It feels like ephemeral environment's time has finally come.

[Solution Source](https://github.com/adamgordonbell/fibhatchery/blob/main/fibfactory.py)
