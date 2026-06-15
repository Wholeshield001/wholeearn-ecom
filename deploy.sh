#!/bin/bash

# Deployment script for wholeearn-ecom
# This script automates the deployment to VPS

# Configuration
VPS_USER="root"
VPS_HOST="72.61.19.120"
VPS_PATH="/srv/shop_app"
PROJECT_NAME="wholeearn-ecom"
DOMAIN="shop.wholeshieldwellness.com"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Deploying $PROJECT_NAME to VPS${NC}"
echo -e "${GREEN}========================================${NC}"

# Check if .env file exists
if [ ! -f .env ]; then
    echo -e "${RED}Error: .env file not found!${NC}"
    echo -e "${YELLOW}Please create a .env file based on .env.example${NC}"
    exit 1
fi

# Build Tailwind CSS
echo -e "${YELLOW}Building Tailwind CSS...${NC}"
python manage.py tailwind build

# Collect static files
echo -e "${YELLOW}Collecting static files...${NC}"
python manage.py collectstatic --noinput

# Run tests (optional - comment out if needed)
# echo -e "${YELLOW}Running tests...${NC}"
# python manage.py test

# Substitute placeholder username in gunicorn service file
sed -i.bak "s/your_vps_username/$VPS_USER/g" deployment/gunicorn.service
rm -f deployment/gunicorn.service.bak

# Create deployment package
echo -e "${YELLOW}Creating deployment package...${NC}"
tar -czf deploy.tar.gz \
    --exclude='env' \
    --exclude='*.pyc' \
    --exclude='__pycache__' \
    --exclude='.git' \
    --exclude='*.sqlite3' \
    --exclude='deploy.tar.gz' \
    --exclude='.env' \
    --exclude='node_modules' \
    --exclude='theme/static_src/node_modules' \
    .

# Restore the placeholder in gunicorn.service to keep git repository clean
git checkout -- deployment/gunicorn.service

# Upload to VPS
echo -e "${YELLOW}Uploading to VPS...${NC}"
scp deploy.tar.gz $VPS_USER@$VPS_HOST:$VPS_PATH/

# Execute deployment on VPS inside a single SSH connection
echo -e "${YELLOW}Executing deployment on VPS...${NC}"
ssh $VPS_USER@$VPS_HOST -T << 'ENDSSH'
    set -e
    VPS_PATH="/srv/shop_app"
    RELEASE_DATE=$(date +%Y%m%d_%H%M%S)
    RELEASE_PATH="$VPS_PATH/releases/$RELEASE_DATE"

    # Create release directory and move the tarball there
    mkdir -p "$RELEASE_PATH"
    mv "$VPS_PATH/deploy.tar.gz" "$RELEASE_PATH/"

    # Extract files
    cd "$RELEASE_PATH"
    tar -xzf deploy.tar.gz
    rm deploy.tar.gz

    # Create virtual environment if it doesn't exist
    if [ ! -f "$VPS_PATH/venv/bin/pip" ]; then
        rm -rf "$VPS_PATH/venv"
        python3 -m venv --without-pip "$VPS_PATH/venv"
        curl -sS https://bootstrap.pypa.io/get-pip.py | "$VPS_PATH/venv/bin/python3"
    fi

    # Activate virtual environment and install dependencies
    source "$VPS_PATH/venv/bin/activate"
    pip install --upgrade pip
    pip install -r requirements.txt

    # Create default .env file if it does not exist
    if [ ! -f "$VPS_PATH/.env" ]; then
        echo "Creating default .env file..."
        echo "SECRET_KEY=django-insecure-vps-default-key-change-me" > "$VPS_PATH/.env"
        echo "DEBUG=False" >> "$VPS_PATH/.env"
        echo "DB_ENGINE=postgres" >> "$VPS_PATH/.env"
        echo "POSTGRES_DB=wholeearn_db" >> "$VPS_PATH/.env"
        echo "POSTGRES_USER=wholeshield_user" >> "$VPS_PATH/.env"
        echo "POSTGRES_PASSWORD=wholeshield@2025" >> "$VPS_PATH/.env"
        echo "POSTGRES_HOST=127.0.0.1" >> "$VPS_PATH/.env"
        echo "ALLOWED_HOSTS=shop.wholeshieldwellness.com,wholeshieldwellness.com" >> "$VPS_PATH/.env"
        echo "CSRF_TRUSTED_ORIGINS=https://shop.wholeshieldwellness.com,https://wholeshieldwellness.com" >> "$VPS_PATH/.env"
    fi

    # Link .env file
    ln -sf "$VPS_PATH/.env" "$RELEASE_PATH/.env"

    # Django commands
    python manage.py migrate --noinput
    python manage.py collectstatic --noinput

    # Update active release symlink
    ln -sfn "$RELEASE_PATH" "$VPS_PATH/current"

    # Create logs directory if not exists
    mkdir -p "$VPS_PATH/logs"

    # Gunicorn service configuration
    sudo cp "$RELEASE_PATH/deployment/gunicorn.service" /etc/systemd/system/wholeearn-shop.service
    sudo systemctl daemon-reload
    sudo systemctl enable wholeearn-shop
    sudo systemctl restart wholeearn-shop || {
        echo "=== GUNICORN STATUS ==="
        sudo systemctl status wholeearn-shop --no-pager || true
        exit 1
    }

    # Nginx configuration
    sudo cp "$RELEASE_PATH/deployment/nginx.conf" /etc/nginx/sites-available/shop.wholeshieldwellness.com
    sudo ln -sf /etc/nginx/sites-available/shop.wholeshieldwellness.com /etc/nginx/sites-enabled/
    
    echo "=== TESTING NGINX CONFIGURATION ==="
    sudo nginx -t || {
        echo "=== NGINX CONFIG TEST FAILED ==="
        exit 1
    }
    
    echo "=== RELOADING NGINX ==="
    sudo systemctl reload nginx

    # Keep only last 5 releases
    cd "$VPS_PATH/releases"
    ls -t | tail -n +6 | xargs -r rm -rf

    echo "Deployment completed successfully!"
ENDSSH

# Clean up local deployment package
rm -f deploy.tar.gz

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Deployment completed!${NC}"
echo -e "${GREEN}  Your app is now live at:${NC}"
echo -e "${GREEN}  https://$DOMAIN${NC}"
echo -e "${GREEN}========================================${NC}"
