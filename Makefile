# Garden-Tiller Makefile

.PHONY: help clean test lint build container run install

SHELL := /bin/bash
PROJECT_ROOT := $(shell pwd)
PYTHON := python3
PIP := $(PYTHON) -m pip
PODMAN := podman
CONTAINER_NAME := garden-tiller
CONTAINER_TAG := latest

help: ## Show this help message
	@echo 'Garden-Tiller: OpenShift Lab Environment Validation Suite'
	@echo ''
	@echo 'Usage:'
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

clean: ## Clean up temporary files
	rm -rf build/ dist/ *.egg-info/ .pytest_cache/ __pycache__/ .coverage htmlcov/
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name "*.pyd" -delete
	find . -type f -name ".coverage.*" -delete

test: ## Run tests
	pytest

lint: ## Run code linting
	pylint scripts library tests

build: ## Build Python package
	$(PYTHON) setup.py sdist bdist_wheel

container: ## Build container image
	$(PODMAN) build -t $(CONTAINER_NAME):$(CONTAINER_TAG) -f docker/Dockerfile .

run: ## Run validation (wrapper for check-lab.sh)
	./check-lab.sh --inventory inventories/sample/hosts.yaml

run-container: container ## Run validation in container
	./check-lab.sh --inventory inventories/sample/hosts.yaml --podman

install: ## Install dependencies
	$(PIP) install -r requirements.txt
	$(PIP) install -e .
