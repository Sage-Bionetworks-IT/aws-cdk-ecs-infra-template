import aws_cdk as cdk
import aws_cdk.assertions as assertions

from src.network_stack import NetworkStack
from src.load_balancer_stack import LoadBalancerStack


def test_load_balancer_stack_created():
    """Test that the load balancer stack creates an ALB with proper security group."""
    cdk_app = cdk.App()
    vpc_cidr = "10.254.192.0/24"

    # Create network stack with security groups
    network_stack = NetworkStack(cdk_app, "NetworkStack", vpc_cidr=vpc_cidr)
    network_stack.configure_security_group_connections(container_port=80)

    # Create load balancer stack
    load_balancer_stack = LoadBalancerStack(
        scope=cdk_app,
        construct_id="LoadBalancerStack",
        vpc=network_stack.vpc,
        alb_security_group=network_stack.alb_security_group,
    )

    template = assertions.Template.from_stack(load_balancer_stack)

    # Check that ALB is created
    template.has_resource_properties(
        "AWS::ElasticLoadBalancingV2::LoadBalancer",
        {
            "Scheme": "internet-facing",
            "Type": "application",
        },
    )

    # Check that WAF WebACL is created
    template.has_resource_properties(
        "AWS::WAFv2::WebACL",
        {
            "Scope": "REGIONAL",
            "DefaultAction": {"Allow": {}},
        },
    )

    # Check that WAF association is created
    template.has_resource("AWS::WAFv2::WebACLAssociation", {})


def test_load_balancer_waf_rules():
    """Test that WAF rules are properly configured."""
    cdk_app = cdk.App()
    vpc_cidr = "10.254.192.0/24"

    network_stack = NetworkStack(cdk_app, "NetworkStack", vpc_cidr=vpc_cidr)
    network_stack.configure_security_group_connections(container_port=80)

    load_balancer_stack = LoadBalancerStack(
        scope=cdk_app,
        construct_id="LoadBalancerStack",
        vpc=network_stack.vpc,
        alb_security_group=network_stack.alb_security_group,
    )

    template = assertions.Template.from_stack(load_balancer_stack)

    # Check that WebACL has the expected managed rule groups
    template.has_resource_properties(
        "AWS::WAFv2::WebACL",
        {
            "Rules": [
                {
                    "Name": "AWSManagedRulesCommonRuleSet",
                    "Priority": 0,
                    "Statement": {
                        "ManagedRuleGroupStatement": {
                            "Name": "AWSManagedRulesCommonRuleSet",
                            "VendorName": "AWS",
                        }
                    },
                },
                {
                    "Name": "AWSManagedRulesKnownBadInputsRuleSet",
                    "Priority": 1,
                    "Statement": {
                        "ManagedRuleGroupStatement": {
                            "Name": "AWSManagedRulesKnownBadInputsRuleSet",
                            "VendorName": "AWS",
                        }
                    },
                },
            ]
        },
    )
