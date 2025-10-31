import aws_cdk as cdk

from aws_cdk import aws_ec2 as ec2

from constructs import Construct


class NetworkStack(cdk.Stack):
    """
    Network for applications
    """

    def __init__(self, scope: Construct, construct_id: str, vpc_cidr, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # -------------------
        # create a VPC
        # -------------------
        self.vpc = ec2.Vpc(
            self, "Vpc", max_azs=2, ip_addresses=ec2.IpAddresses.cidr(vpc_cidr)
        )

        # Create VPC endpoint for GuardDuty
        # This is required for ECS Runtime Monitoring and must be explicitly
        # managed to avoid orphaned resources during stack deletion
        self.guardduty_endpoint = ec2.InterfaceVpcEndpoint(
            self,
            "GuardDutyEndpoint",
            vpc=self.vpc,
            service=ec2.InterfaceVpcEndpointAwsService.GUARDDUTY_DATA,
            # Place endpoints in private subnets for security
            subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            # Enable private DNS to use standard GuardDuty endpoint name
            private_dns_enabled=True,
        )
