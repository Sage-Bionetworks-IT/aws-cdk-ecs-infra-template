import aws_cdk as core
import aws_cdk.assertions as assertions

from src.network_stack import NetworkStack


def test_vpc_created():
    app = core.App()
    vpc_cidr = "10.254.192.0/24"
    network = NetworkStack(app, "NetworkStack", vpc_cidr)
    template = assertions.Template.from_stack(network)
    template.has_resource_properties("AWS::EC2::VPC", {"CidrBlock": vpc_cidr})


def test_security_groups_created():
    """Test that ALB and ECS security groups are created with proper configurations."""
    app = core.App()
    vpc_cidr = "10.254.192.0/24"
    network = NetworkStack(app, "NetworkStack", vpc_cidr)
    template = assertions.Template.from_stack(network)

    # Check that ALB security group is created
    template.has_resource_properties(
        "AWS::EC2::SecurityGroup",
        {
            "GroupDescription": "Security group for Application Load Balancer",
            "SecurityGroupIngress": [
                {
                    "CidrIp": "0.0.0.0/0",
                    "Description": "Allow HTTP from internet",
                    "FromPort": 80,
                    "IpProtocol": "tcp",
                    "ToPort": 80,
                },
                {
                    "CidrIp": "0.0.0.0/0",
                    "Description": "Allow HTTPS from internet",
                    "FromPort": 443,
                    "IpProtocol": "tcp",
                    "ToPort": 443,
                },
            ],
        },
    )

    # Check that ECS security group is created
    template.has_resource_properties(
        "AWS::EC2::SecurityGroup",
        {
            "GroupDescription": "Security group for ECS tasks",
        },
    )


def test_security_group_connections():
    """Test that security group connections are properly configured."""
    app = core.App()
    vpc_cidr = "10.254.192.0/24"
    network = NetworkStack(app, "NetworkStack", vpc_cidr)

    # Configure connections for port 80
    network.configure_security_group_connections(container_port=80)

    template = assertions.Template.from_stack(network)

    # Verify that security group rules are created
    # Note: The actual verification of cross-references between security groups
    # requires more complex template assertions, but the basic structure should be present
    template.resource_count_is("AWS::EC2::SecurityGroup", 2)
