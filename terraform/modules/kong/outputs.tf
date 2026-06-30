output "alb_dns_name"        { value = aws_lb.kong.dns_name }
output "alb_zone_id"         { value = aws_lb.kong.zone_id }
output "alb_arn"             { value = aws_lb.kong.arn }
output "kong_task_role_arn"  { value = aws_iam_role.kong_task.arn }
output "kong_cluster_id"     { value = aws_ecs_cluster.kong.id }
