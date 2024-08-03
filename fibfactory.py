import argparse
import logging
from pulumi import automation as auto
import pulumi
import pulumi_aws as aws
import pulumi_docker as docker

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

PROJECT_NAME = "fibfactory"

def pulumi_program() -> None:
    # Configuration
    config = pulumi.Config()
    app_name = config.require("appName")
    container_port = config.require_int("containerPort")

    # Set the AWS region
    region = "us-west-2"
    aws_provider = aws.Provider("aws-provider", region=region)

    # Build and push Docker image to ECR Public
    image = docker.Image("app-image",
        build=docker.DockerBuildArgs(
            context=".",
            platform="linux/amd64"
        ),
        image_name=f"public.ecr.aws/o2l3o3x9/adamgordonbell:{app_name}",
        registry=docker.RegistryArgs(
            server="public.ecr.aws"
        ),
        opts=pulumi.ResourceOptions(provider=aws_provider)
    )

    # Create App Runner service
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
        opts=pulumi.ResourceOptions(provider=aws_provider, depends_on=[image])
    )

    # Outputs
    pulumi.export("app_runner_service_url", app_runner_service.service_url)

def create_env(env_id: str) -> None:
    stack_name = f"{PROJECT_NAME}-{env_id}"
    
    try:
        stack = auto.create_or_select_stack(stack_name=stack_name,
                                            project_name=PROJECT_NAME,
                                            program=pulumi_program)

        logger.info(f"Successfully initialized stack {stack_name}")
        
        # Set required configuration
        stack.set_config("appName", auto.ConfigValue(value=f"fib-app-{env_id}"))
        stack.set_config("containerPort", auto.ConfigValue(value="8080"))
        
        logger.info("Config set")

        # Deploy the stack
        logger.info("Deploying the stack...")
        up_res = stack.up(on_output=lambda msg: logger.info(msg))
        
        service_url = up_res.outputs.get('app_runner_service_url', {}).value

        logger.info(f"Stack {stack_name} created successfully")
        logger.info(f"Service URL: {service_url}")
    except Exception as e:
        logger.error(f"Error creating stack: {str(e)}", exc_info=True)
        raise

def destroy_env(env_id: str) -> None:
    stack_name = f"{PROJECT_NAME}-{env_id}"
    
    try:
        stack = auto.select_stack(stack_name=stack_name,
                                  project_name=PROJECT_NAME,
                                  program=pulumi_program)
        
        logger.info(f"Destroying stack {stack_name}")
        
        destroy_result = stack.destroy(on_output=lambda msg: logger.info(msg))
        
        if destroy_result.summary.resource_changes:
            logger.info(f"Resources destroyed: {destroy_result.summary.resource_changes}")
        
        logger.info(f"Stack {stack_name} destroyed successfully")
        
        # Remove the stack completely
        stack.workspace.remove_stack(stack_name)
        
        logger.info(f"Stack {stack_name} removed completely")
    except auto.errors.StackNotFoundError:
        logger.error(f"Stack {stack_name} not found. It may have already been destroyed.")
    except Exception as e:
        logger.error(f"Error destroying stack: {str(e)}", exc_info=True)

def list_envs() -> None:
    try:
        workspace = auto.LocalWorkspace(project_settings=auto.ProjectSettings(name=PROJECT_NAME, runtime="python"))
        stacks = workspace.list_stacks()
        print("Active environments:")
        for stack in stacks:
            if stack.name.startswith(PROJECT_NAME):
                print(f"- {stack.name}")
        if not any(stack.name.startswith(PROJECT_NAME) for stack in stacks):
            print("No active environments found.")
    except Exception as e:
        logger.error(f"Error listing environments: {str(e)}", exc_info=True)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Manage Fibonacci service environments")
    parser.add_argument("action", choices=["create", "destroy", "list"], help="Action to perform")
    parser.add_argument("--env-id", help="Environment ID (required for create and destroy)")
    
    args = parser.parse_args()
    
    if args.action == "create":
        if not args.env_id:
            print("Error: --env-id is required for create action")
        else:
            create_env(args.env_id)
    elif args.action == "destroy":
        if not args.env_id:
            print("Error: --env-id is required for destroy action")
        else:
            destroy_env(args.env_id)
    elif args.action == "list":
        list_envs()
