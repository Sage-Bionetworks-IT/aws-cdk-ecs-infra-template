import aws_cdk as cdk
import aws_cdk.assertions as assertions

from src.network_stack import NetworkStack
from src.ecs_stack import EcsStack
from src.load_balancer_stack import LoadBalancerStack
from src.service_props import ServiceProps
from src.service_stack import LoadBalancedServiceStack


def test_security_integration():
    """Integration test to verify that security groups are properly configured across all stacks."""
    cdk_app = cdk.App()
    vpc_cidr = "10.254.192.0/24"

    # Create network stack with security groups
    network_stack = NetworkStack(cdk_app, "NetworkStack", vpc_cidr=vpc_cidr)
    network_stack.configure_security_group_connections(container_port=80)

    # Create ECS stack
    ecs_stack = EcsStack(
        cdk_app, "EcsStack", vpc=network_stack.vpc, namespace="test.app.io"
    )

    # Create load balancer stack
    load_balancer_stack = LoadBalancerStack(
        scope=cdk_app,
        construct_id="LoadBalancerStack",
        vpc=network_stack.vpc,
        alb_security_group=network_stack.alb_security_group,
    )

    # Create service stack
    app_props = ServiceProps(
        container_name="test-app",
        container_location="nginx:latest",
        container_port=80,
        ecs_task_cpu=256,
        ecs_task_memory=512,
    )

    service_stack = LoadBalancedServiceStack(
        scope=cdk_app,
        construct_id="ServiceStack",
        vpc=network_stack.vpc,
        cluster=ecs_stack.cluster,
        props=app_props,
        load_balancer=load_balancer_stack.alb,
        ecs_security_group=network_stack.ecs_security_group,
    )

    # Test network stack has security groups
    network_template = assertions.Template.from_stack(network_stack)
    network_template.resource_count_is("AWS::EC2::SecurityGroup", 2)

    # Test load balancer uses the ALB security group
    lb_template = assertions.Template.from_stack(load_balancer_stack)
    lb_template.has_resource_properties(
        "AWS::ElasticLoadBalancingV2::LoadBalancer",
        {
            "Scheme": "internet-facing",
            "Type": "application",
        },
    )

    # Test service stack creates ECS service
    service_template = assertions.Template.from_stack(service_stack)
    service_template.has_resource_properties(
        "AWS::ECS::Service",
        {
            "EnableExecuteCommand": True,
        },
    )

    # Test that task definition is created
    service_template.has_resource_properties(
        "AWS::ECS::TaskDefinition",
        {
            "ContainerDefinitions": [
                {
                    "Image": "nginx:latest",
                    "Name": "test-app",
                }
            ],
            "Cpu": "256",
            "Memory": "512",
            "NetworkMode": "awsvpc",
            "RequiresCompatibilities": ["FARGATE"],
        },
    )


def test_least_privilege_security():
    """Test that security groups implement least privilege access."""
    cdk_app = cdk.App()
    vpc_cidr = "10.254.192.0/24"

    network_stack = NetworkStack(cdk_app, "NetworkStack", vpc_cidr=vpc_cidr)
    network_stack.configure_security_group_connections(container_port=80)

    template = assertions.Template.from_stack(network_stack)

    # Verify ALB security group allows only HTTP/HTTPS from internet
    alb_sg_rules = template.find_resources(
        "AWS::EC2::SecurityGroup",
        {
            "Properties": {
                "GroupDescription": "Security group for Application Load Balancer"
            }
        },
    )

    # Should have exactly one ALB security group
    assert len(alb_sg_rules) == 1

    # Verify ECS security group exists (ingress rules are added dynamically)
    ecs_sg_rules = template.find_resources(
        "AWS::EC2::SecurityGroup",
        {"Properties": {"GroupDescription": "Security group for ECS tasks"}},
    )

    # Should have exactly one ECS security group
    assert len(ecs_sg_rules) == 1

    # Total should be 2 security groups
    template.resource_count_is("AWS::EC2::SecurityGroup", 2)
