import aws_cdk as cdk

from aws_cdk import aws_ec2 as ec2

from constructs import Construct


class NetworkStack(cdk.Stack):
    """
    Network for applications with security groups configured for least privilege access
    """

    def __init__(self, scope: Construct, construct_id: str, vpc_cidr, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # -------------------
        # create a VPC
        # -------------------
        self.vpc = ec2.Vpc(
            self, "Vpc", max_azs=2, ip_addresses=ec2.IpAddresses.cidr(vpc_cidr)
        )

        # -------------------
        # Create security groups with least privilege access
        # -------------------

        # ALB Security Group - allows traffic from internet on HTTP/HTTPS
        self.alb_security_group = ec2.SecurityGroup(
            self,
            "AlbSecurityGroup",
            vpc=self.vpc,
            description="Security group for Application Load Balancer",
            allow_all_outbound=False,  # Restrict outbound traffic
        )

        # Allow HTTP from internet (required for public ALB)
        self.alb_security_group.add_ingress_rule(
            peer=ec2.Peer.ipv4("0.0.0.0/0"),
            connection=ec2.Port.tcp(80),
            description="Allow HTTP from internet",
        )

        # Allow HTTPS from internet (required for public ALB)
        self.alb_security_group.add_ingress_rule(
            peer=ec2.Peer.ipv4("0.0.0.0/0"),
            connection=ec2.Port.tcp(443),
            description="Allow HTTPS from internet",
        )

        # ECS Security Group - allows traffic only from ALB
        self.ecs_security_group = ec2.SecurityGroup(
            self,
            "EcsSecurityGroup",
            vpc=self.vpc,
            description="Security group for ECS tasks",
            allow_all_outbound=True,  # ECS tasks need outbound for pulling images, etc.
        )

    def configure_security_group_connections(self, container_port: int) -> None:
        """
        Configure security group connections between ALB and ECS for the specified container port.
        This uses separate SecurityGroupEgress and SecurityGroupIngress resources to avoid circular dependencies.
        """
        # Create explicit security group rules to avoid circular dependencies

        # Allow ALB to send traffic to ECS containers
        ec2.CfnSecurityGroupEgress(
            self,
            f"AlbToEcsEgress{container_port}",
            group_id=self.alb_security_group.security_group_id,
            ip_protocol="tcp",
            from_port=container_port,
            to_port=container_port,
            destination_security_group_id=self.ecs_security_group.security_group_id,
            description=f"Allow outbound to ECS containers on port {container_port}",
        )

        # Allow ECS containers to receive traffic from ALB
        ec2.CfnSecurityGroupIngress(
            self,
            f"EcsFromAlbIngress{container_port}",
            group_id=self.ecs_security_group.security_group_id,
            ip_protocol="tcp",
            from_port=container_port,
            to_port=container_port,
            source_security_group_id=self.alb_security_group.security_group_id,
            description=f"Allow traffic from ALB on port {container_port}",
        )
