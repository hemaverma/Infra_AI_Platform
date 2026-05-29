# Use the official Azure Functions Python base image
ARG PYTHON_VERSION=3.10
FROM mcr.microsoft.com/azure-functions/python:4-python${PYTHON_VERSION}

# Set environment variables
ENV AzureWebJobsScriptRoot=/home/site/wwwroot \
    AzureFunctionsJobHost__Logging__Console__IsEnabled=true \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Set working directory
WORKDIR /home/site/wwwroot

# Copy requirements file
COPY requirements.txt /home/site/wwwroot/

# Install Python dependencies
# Note: agent-framework requires --pre flag for pre-release versions
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --pre -r requirements.txt

# Copy the function app code
COPY src/ /home/site/wwwroot/

# Ensure proper permissions
RUN chmod -R 755 /home/site/wwwroot

# Expose port (Azure Functions default)
EXPOSE 80

# The base image already has the CMD to run the Functions host
