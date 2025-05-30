#!/usr/bin/env python3
"""
Garden-Tiller Report Generator
Generates HTML reports summarizing lab validation results
Uses PyBreaker for resilience and Structlog for logging
"""

import os
import sys
import json
import argparse
import datetime
import traceback
import time
from pathlib import Path
import functools

try:
    import jinja2
    import pybreaker
    import logging
    import structlog
    from structlog.stdlib import LoggerFactory
    from structlog.processors import TimeStamper
    import rich.console
except ImportError:
    print("Required dependencies not found. Please install them with:")
    print("pip install jinja2 pybreaker structlog rich")
    sys.exit(1)

# Set up structured logging
def setup_logging(log_file=None, level=logging.INFO):
    """Configure structlog for the application"""
    console = rich.console.Console()
    
    # Set up standard library logging
    logging.basicConfig(
        format="%(message)s",
        level=level,
    )
    
    # File handler (if log_file provided)
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(level)
        logging.getLogger().addHandler(file_handler)
    
    # Configure processors for structlog
    processors = [
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.stdlib.render_to_log_kwargs,
    ]
    
    if log_file:
        # JSON format for file
        file_processor = structlog.processors.JSONRenderer()
    else:
        # Colored console output
        file_processor = structlog.dev.ConsoleRenderer(colors=True)
    
    structlog.configure(
        processors=processors + [file_processor],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    
    return structlog.get_logger("garden-tiller")


# Configure circuit breaker
breaker = pybreaker.CircuitBreaker(
    fail_max=5,
    reset_timeout=30,
    exclude=[ValueError, KeyError]  # Don't trip the breaker on these exceptions
)

# Custom decorator for retries with exponential backoff
def retry_with_backoff(max_tries=3, initial_delay=1):
    """Retry a function with exponential backoff"""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            attempts = 0
            backoff = initial_delay
            
            while attempts < max_tries:
                try:
                    return func(*args, **kwargs)
                except pybreaker.CircuitBreakerError:
                    # Don't retry if the circuit is open
                    raise
                except Exception as e:
                    attempts += 1
                    if attempts == max_tries:
                        raise
                    # Exponential backoff
                    time.sleep(backoff)
                    backoff *= 2
            return func(*args, **kwargs)
        return wrapper
    return decorator


class ReportGenerator:
    """Generate HTML reports based on validation results"""
    
    def __init__(self, results_file, output_file, logger):
        self.results_file = results_file
        self.output_file = output_file
        self.logger = logger
        # Use direct path to templates in the scripts directory
        self.template_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "templates"
        )
        self.results = None
    
    @retry_with_backoff(max_tries=3, initial_delay=1)
    @breaker
    def load_results(self):
        """Load validation results with resilience patterns"""
        try:
            self.logger.info("Loading results from file", file=self.results_file)
            with open(self.results_file, 'r') as f:
                self.results = json.load(f)
            return True
        except Exception as e:
            self.logger.error("Failed to load results", error=str(e))
            self.logger.debug(traceback.format_exc())
            raise
    
    @retry_with_backoff(max_tries=3, initial_delay=1)
    @breaker
    def generate_html_report(self):
        """Generate HTML report with resilience patterns"""
        try:
            if not self.results:
                self.logger.error("No results loaded")
                return False
            
            self.logger.info("Generating HTML report", output=self.output_file)
            
            # Create template environment
            env = jinja2.Environment(
                loader=jinja2.FileSystemLoader(self.template_dir)
            )
            template = env.get_template("report_template.html")
            
            # Calculate summary stats
            total_checks = sum(
                section.get("total_checks", 0) 
                for section in self.results.values()
            )
            passed_checks = sum(
                section.get("passed_checks", 0) 
                for section in self.results.values()
            )
            failed_checks = sum(
                section.get("failed_checks", 0) 
                for section in self.results.values()
            )
            warning_checks = sum(
                section.get("warning_checks", 0) 
                for section in self.results.values()
            )
            
            success_rate = 0
            if total_checks > 0:
                success_rate = (passed_checks / total_checks) * 100
            
            # Render template
            html_content = template.render(
                results=self.results,
                timestamp=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                total_checks=total_checks,
                passed_checks=passed_checks,
                failed_checks=failed_checks,
                warning_checks=warning_checks,
                success_rate=success_rate
            )
            
            # Write to output file
            os.makedirs(os.path.dirname(self.output_file), exist_ok=True)
            with open(self.output_file, 'w') as f:
                f.write(html_content)
            
            self.logger.info("Report generation completed successfully")
            return True
            
        except Exception as e:
            self.logger.error("Failed to generate report", error=str(e))
            self.logger.debug(traceback.format_exc())
            raise
    
    @retry_with_backoff(max_tries=3, initial_delay=1)
    @breaker
    def generate_diagram(self):
        """Generate network topology diagram with resilience patterns"""
        try:
            if not self.results:
                self.logger.error("No results loaded")
                return False
                
            self.logger.info("Generating network topology diagram")
            # This would integrate with a diagram generation library
            # For now, we'll just create a placeholder for the concept
            
            diagram_file = os.path.join(
                os.path.dirname(self.output_file),
                "network_topology.png"
            )
            
            # In a real implementation, this would use something like:
            # - graphviz
            # - networkx + matplotlib
            # - diagrams library
            # to create an actual network topology diagram
            
            self.logger.info("Diagram would be saved", file=diagram_file)
            return True
            
        except Exception as e:
            self.logger.error("Failed to generate diagram", error=str(e))
            self.logger.debug(traceback.format_exc())
            raise


def main():
    parser = argparse.ArgumentParser(
        description="Garden-Tiller Report Generator"
    )
    parser.add_argument(
        "--results", "-r",
        required=True,
        help="JSON file containing validation results"
    )
    parser.add_argument(
        "--output", "-o",
        required=True,
        help="Output HTML report file"
    )
    parser.add_argument(
        "--log-file", "-l",
        help="Log file path"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging"
    )
    
    args = parser.parse_args()
    
    # Set up logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logger = setup_logging(args.log_file, log_level)
    
    logger.info("Starting Garden-Tiller Report Generator")
    
    # Create report generator
    generator = ReportGenerator(args.results, args.output, logger)
    
    # Generate report
    if generator.load_results():
        generator.generate_html_report()
        generator.generate_diagram()
    
    logger.info("Report generation completed")


if __name__ == "__main__":
    main()
