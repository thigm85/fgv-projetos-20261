provider "aws" {
  region = "us-west-2"
}

# /* criando rede virtual privada */

# resource "aws_vpc" "dumb_vpc" {
#     cidr_block = "10.0.0.0/16"
#     enable_dns_support = true
#     enable_dns_hostnames = true

#     tags = {
#         Name = "dumb_vpc"
#     }
# }

# resource "aws_internet_gateway" "gw" {
#     vpc_id = aws_vpc.dumb_vpc.id
# }

# /* fazendo a rede virtual falar com toda a internet */

# resource "aws_subnet" "dumb_subnet" {
#     vpc_id = aws_vpc.dumb_vpc.id
#     cidr_block = "10.0.1.0/24"
#     map_public_ip_on_launch = true
# }

# resource "aws_route_table" "public_rt" {
#     vpc_id = aws_vpc.dumb_vpc.id

#     route {
#         cidr_block = "0.0.0.0/0"
#         gateway_id = aws_internet_gateway.gw.id
#     }
# }

# resource "aws_route_table_association" "dumb_association" {
#     subnet_id = aws_subnet.dumb_subnet.id
#     route_table_id = aws_route_table.public_rt.id
# }

/* criando security group que fala com a internet pro banco */

resource "aws_security_group" "dumb_sg" {
    name = "public security group"

    ingress {
        from_port = 3306
        to_port = 3306
        protocol = "tcp"
        cidr_blocks = ["0.0.0.0/0"]
    }
}

/* finalmente criando o banco */

resource "aws_db_instance" "cars_database" {
  allocated_storage    = 10
  apply_immediately    = true
  db_name              = "classicmodels"
  engine               = "mysql"
  engine_version       = "8.0"
  instance_class       = "db.t3.micro"
  username             = "admin_user"
  password             = "ihateavroformat69"
  parameter_group_name = "default.mysql8.0"
  port = 3306
  publicly_accessible  = true
  skip_final_snapshot  = true
  vpc_security_group_ids = [aws_security_group.dumb_sg.id]
}
