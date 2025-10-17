import aws_cdk as core
import aws_cdk.assertions as assertions

from src.network_stack import NetworkStack
from src.utils import load_context_config


def test_vpc_created():
    # Load configuration from dev environment
    config = load_context_config(env_name="dev")

    app = core.App()
    vpc_cidr = config["VPC_CIDR"]
    network = NetworkStack(app, "NetworkStack", vpc_cidr)
    template = assertions.Template.from_stack(network)
    template.has_resource_properties("AWS::EC2::VPC", {"CidrBlock": vpc_cidr})
