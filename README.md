# FibFactory

FibFactory is a project that demonstrates the use of Pulumi Automation API to create and manage ephemeral Fibonacci service environments using AWS App Runner.


## Usage

To create a new environment:
```
poetry run python fibfactory.py create --env-id <environment-id>
```

To list all environments:
```
poetry run python fibfactory.py list
```

To destroy an environment:
```
poetry run python fibfactory.py destroy --env-id <environment-id>
```
