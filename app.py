import aws_cdk as cdk

from src.ecs_stack import EcsStack
from src.load_balancer_stack import LoadBalancerStack
from src.network_stack import NetworkStack
from src.service_props import ServiceProps
from src.service_stack import LoadBalancedServiceStack
from src.utils import load_context_config


cdk_app = cdk.App()
env_name = cdk_app.node.try_get_context("env")
config = load_context_config(env_name=env_name)
stack_name_prefix = f"app-{env_name}"
fully_qualified_domain_name = config["FQDN"]
environment_tags = config["TAGS"]
app_version = "edge"

# recursively apply tags to all stack resources
if environment_tags:
    for key, value in environment_tags.items():
        cdk.Tags.of(cdk_app).add(key, value)

network_stack = NetworkStack(
    scope=cdk_app,
    construct_id=f"{stack_name_prefix}-network",
    vpc_cidr=config["VPC_CIDR"],
)

ecs_stack = EcsStack(
    scope=cdk_app,
    construct_id=f"{stack_name_prefix}-ecs",
    vpc=network_stack.vpc,
    namespace=fully_qualified_domain_name,
)

# From AWS docs https://docs.aws.amazon.com/AmazonECS/latest/developerguide/service-connect-concepts-deploy.html
# The public discovery and reachability should be created last by AWS CloudFormation, including the frontend
# client service. The services need to be created in this order to prevent an time period when the frontend
# client service is running and available the public, but a backend isn't.
load_balancer_stack = LoadBalancerStack(
    scope=cdk_app,
    construct_id=f"{stack_name_prefix}-load-balancer",
    vpc=network_stack.vpc,
)

app_props = ServiceProps(
    ecs_task_cpu=256,
    ecs_task_memory=512,
    container_name="my-app",
    container_location=f"ghcr.io/sage-bionetworks/my-app:{app_version}",
    container_port=80,
    container_env_vars={
        "APP_VERSION": f"{app_version}",
    },
)
app_stack = LoadBalancedServiceStack(
    scope=cdk_app,
    construct_id=f"{stack_name_prefix}-app",
    vpc=network_stack.vpc,
    cluster=ecs_stack.cluster,
    props=app_props,
    load_balancer=load_balancer_stack.alb,
    certificate_arn=config["CERTIFICATE_ARN"],
    health_check_path="/health",
)
app_stack.add_dependency(app_stack)

cdk_app.synth()
