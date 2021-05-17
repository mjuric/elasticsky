PROJECT_ID?=moeyens-thor-dev
ZONE?=us-west1-a
IMAGE_NAME?=ray-thin

validate:
	@ IMAGE_NAME=$(IMAGE_NAME) ZONE=$(ZONE) PROJECT_ID=$(PROJECT_ID) packer validate packer.json
	@ echo "Validation passed. Run 'make image' to build the image"

image:
	IMAGE_NAME=$(IMAGE_NAME) ZONE=$(ZONE) PROJECT_ID=$(PROJECT_ID) packer build packer.json

delete:
	@ gcloud compute images delete $(IMAGE_NAME)
