#!/bin/bash
# deploy.sh

# Exit immediately if a command exits with a non-zero status
set -e

echo "Starting deployment process..."

# Update system
echo "Updating system packages..."
apt update && apt upgrade -y

# Install dependencies
echo "Installing required packages..."
apt install -y python3-pip python3-venv nginx

# Create directory structure
echo "Creating directory structure..."
mkdir -p /var/www/roommates-app
mkdir -p /var/www/roommates-app/data/db
mkdir -p /var/www/roommates-app/static/profile_images

# Copy application files to the deployment directory
echo "Copying application files..."
cp -r ./* /var/www/roommates-app/

# Setup virtual environment
echo "Setting up Python virtual environment..."
cd /var/www/roommates-app
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Create uploads directory and set permissions
echo "Setting proper permissions..."
chown -R www-data:www-data /var/www/roommates-app
chmod -R 755 /var/www/roommates-app

# Set environment variables
echo "Setting environment variables..."
cat > /etc/environment <<EOL
SECRET_KEY="$(openssl rand -hex 24)"
DATABASE_PATH="/var/www/roommates-app/data/db/roommates.db"
UPLOAD_FOLDER="/var/www/roommates-app/static/profile_images"
FLASK_ENV="production"
EOL

# Load the new environment variables
source /etc/environment

# Initialize the database
echo "Initializing database..."
python init_db.py

# Setup systemd service
echo "Setting up systemd service..."
cat > /etc/systemd/system/roommates.service <<EOL
[Unit]
Description=Roommates Finance App
After=network.target

[Service]
User=www-data
WorkingDirectory=/var/www/roommates-app
Environment="PATH=/var/www/roommates-app/venv/bin"
Environment="SECRET_KEY=${SECRET_KEY}"
Environment="DATABASE_PATH=${DATABASE_PATH}"
Environment="UPLOAD_FOLDER=${UPLOAD_FOLDER}"
Environment="FLASK_ENV=production"
ExecStart=/var/www/roommates-app/venv/bin/gunicorn --workers 3 --bind 0.0.0.0:8000 wsgi:app
Restart=always

[Install]
WantedBy=multi-user.target
EOL

systemctl daemon-reload
systemctl enable roommates
systemctl start roommates

# Setup Nginx
echo "Configuring Nginx..."
DROPLET_IP=$(curl -s http://169.254.169.254/metadata/v1/interfaces/public/0/ipv4/address)
cat > /etc/nginx/sites-available/roommates-app.conf <<EOL
server {
    listen 80;
    server_name ${DROPLET_IP};

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    location /static {
        alias /var/www/roommates-app/static;
    }
}
EOL

ln -s /etc/nginx/sites-available/roommates-app.conf /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
systemctl restart nginx

# Setup firewall
echo "Configuring firewall..."
ufw allow 'Nginx Full'
ufw allow ssh
ufw --force enable

echo "Deployment complete!"
echo "Your application is now running at: http://${DROPLET_IP}"