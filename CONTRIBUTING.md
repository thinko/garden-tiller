# Contributing to Garden-Tiller

Thank you for your interest in contributing to Garden-Tiller. This document outlines some guidelines for contributing to this project.

## Code of Conduct

Please be respectful of other contributors and maintainers. We aim to foster an inclusive and welcoming community.

## How to Contribute

1. **Fork the Repository**: Start by forking the repository on GitHub.

2. **Clone Your Fork**: Clone your fork to your local machine.
   ```bash
   git clone https://github.com/yourusername/garden-tiller.git
   cd garden-tiller
   ```

3. **Create a Branch**: Create a branch for your work.
   ```bash
   git checkout -b feature/your-feature-name
   ```

4. **Make Your Changes**: Implement your changes, following the project style and conventions.

5. **Test Your Changes**: Ensure your changes work as expected and don't break existing functionality.
   ```bash
   ./test-structure.sh
   ```

6. **Commit Your Changes**: Commit your changes with a clear message.
   ```bash
   git commit -m "Add feature X" -m "Description of what this feature does"
   ```

7. **Push to Your Fork**: Push your changes to your fork on GitHub.
   ```bash
   git push origin feature/your-feature-name
   ```

8. **Open a Pull Request**: Open a pull request from your fork to the main repository.

## Development Environment

1. **Set Up Your Environment**:
   ```bash
   # Create a virtual environment
   python -m venv venv
   source venv/bin/activate
   
   # Install dependencies
   pip install -r requirements.txt
   ```

2. **Running Tests**:
   ```bash
   ./test-structure.sh
   ```

## Style Guidelines

- Follow PEP 8 for Python code
- Use 4 spaces for indentation
- Include docstrings for all functions and classes
- Write descriptive commit messages

## Adding Validations

When adding a new validation:

1. Create a new playbook in the `playbooks/` directory
2. Add your validation to `site.yaml`
3. Update the `check-lab.sh` script if necessary
4. Document your validation in the README.md

## Creating Reports

Reports should be HTML files saved to the `reports/` directory. Use the provided templates for consistency.

## Questions or Issues?

If you have any questions or encounter any issues, please open an issue on GitHub.
