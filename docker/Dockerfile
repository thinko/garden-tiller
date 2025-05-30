# Garden-Tiller: Lab Validation Suite
# Containerized execution environment
FROM registry.access.redhat.com/ubi9/ubi-minimal:latest

LABEL maintainer="Your Name <your.email@example.com>"
LABEL description="Garden-Tiller - OpenShift Lab Environment Validation Suite"
LABEL version="1.0.0"

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV ANSIBLE_HOST_KEY_CHECKING=False

# Create app directory
WORKDIR /app

# Install dependencies
RUN microdnf update -y && \
    microdnf install -y \
    # Core tools
    python39 python39-pip \
    # Common utilities
    openssh-clients iputils iproute \
    # Hardware management
    ipmitool \
    # Network tools
    nmap tcpdump bind-utils net-tools \
    # System tools
    procps-ng util-linux which \
    # Build dependencies
    gcc python39-devel && \
    microdnf clean all

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies
RUN python3 -m pip install --no-cache-dir --upgrade pip && \
    python3 -m pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Make scripts executable
RUN chmod +x /app/check-lab.sh
RUN chmod +x /app/scripts/*.py

# Set entrypoint
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]

# Default command (if no command provided at runtime)
CMD ["ansible-playbook", "playbooks/site.yaml"]
