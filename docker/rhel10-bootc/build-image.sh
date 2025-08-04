#!/bin/bash

# 1. Log in to Red Hat registry
podman login registry.redhat.io

# 2. Build the bootc container
podman build -t localhost/diag-bootc:latest .

# 3. Prepare SSH user config (optional)
# key = "ssh-rsa AAAA...your_key_here"
cat > config.toml <<EOF
[[customizations.user]]
name = "ansible"
key = "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQCqKIcXgCs6I2Bz4Q01TIwEtlxAOAVdX9E8bIAwEad8ASehwJba7KMPwS7Q5sDl300YSV6j7HsCZNMfnK+zGjd4i9OIXjT1rLJD4XqsWLSevURySswJgbdIiZluWKS0CDNpGay363H5qU02iiaV9+WA5U7VHv3uMTId3jl/paoXlnZEcSUOenjDa67FFqpygmCDRxKEztAVFLUIkqvQOgwgvns3erg1Prx956Z1C7Q1HSbkkoYdWpjRHrT0LJ+hefyGICTguZjtePHtWwm/f4D/mB5Kx0yMHDcAgHiIW5RzneT1+vh5xYm7G+Am6gLFJM6leYryGVELCMwzQrtD56Px Home Lab"
groups = ["wheel"]
EOF

# 4. Convert to ISO or QCOW2
podman pull registry.redhat.io/rhel10/bootc-image-builder

podman run --rm -it --privileged \
  -v "$(pwd)/config.toml":/config.toml:ro \
  -v "$(pwd)/output":/output \
  -v /var/lib/containers/storage:/var/lib/containers/storage \
  registry.redhat.io/rhel10/bootc-image-builder:latest \
  --type iso \
  --config /config.toml \
  localhost/diag-bootc:latest
