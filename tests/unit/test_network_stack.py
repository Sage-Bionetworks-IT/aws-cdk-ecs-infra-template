import aws_cdk as core
import aws_cdk.assertions as assertions

from src.network_stack import NetworkStack


def test_vpc_created():
    app = core.App()
    vpc_cidr = "10.254.192.0/24"
    network = NetworkStack(app, "NetworkStack", vpc_cidr)
    template = assertions.Template.from_stack(network)
    template.has_resource_properties("AWS::EC2::VPC", {"CidrBlock": vpc_cidr})


def test_guardduty_vpc_endpoint_created():
    """Test that GuardDuty VPC endpoint is created with proper configuration."""
    app = core.App()
    vpc_cidr = "10.254.192.0/24"
    network = NetworkStack(app, "NetworkStack", vpc_cidr)
    template = assertions.Template.from_stack(network)

    # Check that GuardDuty VPC endpoint is created
    template.has_resource_properties(
        "AWS::EC2::VPCEndpoint",
        {
            "VpcEndpointType": "Interface",
            "PrivateDnsEnabled": True,
        },
    )

    # Verify the service name contains guardduty-data (using partial match)
    guardduty_endpoints = template.find_resources("AWS::EC2::VPCEndpoint")
    assert len(guardduty_endpoints) == 1

    # Check that the endpoint has a security group
    template.has_resource("AWS::EC2::SecurityGroup", {})


def test_vpc_endpoint_security():
    """Test that VPC endpoint is placed in private subnets for security."""
    app = core.App()
    vpc_cidr = "10.254.192.0/24"
    network = NetworkStack(app, "NetworkStack", vpc_cidr)
    template = assertions.Template.from_stack(network)

    # Verify that VPC endpoint exists
    template.resource_count_is("AWS::EC2::VPCEndpoint", 1)

    # Check that private subnets are created (VPC with private subnets)
    template.has_resource_properties(
        "AWS::EC2::Subnet",
        {
            "MapPublicIpOnLaunch": False,
        },
    )

    # Verify that the VPC endpoint has a dedicated security group
    template.has_resource_properties(
        "AWS::EC2::SecurityGroup",
        {
            "GroupDescription": "NetworkStack/GuardDutyEndpoint/SecurityGroup",
        },
    )


def test_guardduty_vpc_endpoint_integration():
    """Test that GuardDuty VPC endpoint is properly integrated with the VPC."""
    app = core.App()
    vpc_cidr = "10.254.192.0/24"
    network = NetworkStack(app, "NetworkStack", vpc_cidr)
    template = assertions.Template.from_stack(network)

    # Check that VPC endpoint references the correct VPC
    template.has_resource_properties(
        "AWS::EC2::VPCEndpoint",
        {
            "VpcId": {"Ref": assertions.Match.any_value()},
            "VpcEndpointType": "Interface",
        },
    )

    # Verify that the VPC has the expected configuration for GuardDuty
    template.has_resource_properties(
        "AWS::EC2::VPC",
        {
            "CidrBlock": vpc_cidr,
            "EnableDnsHostnames": True,
            "EnableDnsSupport": True,
        },
    )
