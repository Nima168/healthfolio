# Password-reset emails through Amazon SES. AWS emails the sender address a verification link: the
# address can send only after the link is clicked. New accounts start in the SES sandbox, where mail
# is delivered only to verified addresses until production access is granted (AWS console request).
resource "aws_sesv2_email_identity" "sender" {
  email_identity = var.sender_email
}

# Read by the server at each start (start-app.sh), so email can be switched without a new server.
resource "aws_ssm_parameter" "email_backend" {
  name  = "/${var.name}/email_backend"
  type  = "String"
  value = "ses"
}

resource "aws_ssm_parameter" "email_from" {
  name  = "/${var.name}/email_from"
  type  = "String"
  value = "Healthfolio <${var.sender_email}>"
}
