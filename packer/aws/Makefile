
AMI_NAME?=elasticsky-fastapi

validate:
	@ AMI_NAME=$(AMI_NAME) packer validate ray-ami.json
	@ echo "Validation passed. Run 'make ami' to build the AMI"

ami:
	AMI_NAME=$(AMI_NAME) packer build ray-ami.json

imageid:
	@ aws ec2 describe-images --filters "Name=name,Values=$(AMI_NAME)" --query 'sort_by(Images, &CreationDate)[].ImageId' --output text

delete:
	@ echo "To delete $(AMI_NAME): verify that the command below makes sense, then run it."
	@ echo "delete-ami -r us-west-2 -a $(shell make imageid)"
