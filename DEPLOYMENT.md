# Deployment Guide for wholeearn-ecom

## Prerequisites on VPS

1. **Update system and install dependencies:**
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install python3 python3-pip python3-venv nginx supervisor git -y
```

2. **Install Certbot for SSL:**
```bash
sudo apt install certbot python3-certbot-nginx -y
```

3. **Create deployment user (optional but recommended):**
```bash
sudo adduser deploy
sudo usermod -aG sudo deploy
su - deploy
```

## Initial Setup

1. **Configure DNS:**
   - Point `shop.wholeshieldwellness.com` to your VPS IP address
   - Create an A record in your DNS settings

2. **Clone repository to VPS (first time only):**
```bash
mkdir -p /home/your_vps_username/shop_app
cd /home/your_vps_username/shop_app
git clone YOUR_REPO_URL .
```

3. **Create logs directory:**
```bash
mkdir -p /home/your_vps_username/shop_app/logs
```

4. **Setup environment file on VPS:**
```bash
cp .env.example .env
nano .env  # Edit with your production values
```

## SSL Certificate Setup

```bash
sudo certbot --nginx -d shop.wholeshieldwellness.com
```

Follow the prompts to obtain SSL certificate.

## Local Deployment

1. **Update configuration files:**
   - Edit `deploy.sh` and replace:
     - `your_vps_username` with your actual VPS username
     - `your_vps_ip_or_domain` with your VPS IP or domain
   
   - Edit `deployment/gunicorn.service` and replace:
     - `your_vps_username` with your actual VPS username
   
   - Edit `deployment/nginx.conf` and replace:
     - `your_vps_username` with your actual VPS username

2. **Make deployment script executable:**
```bash
chmod +x deploy.sh
```

3. **Create production .env file:**
```bash
cp .env.example .env
# Edit .env with production values
```

4. **Run deployment:**
```bash
./deploy.sh
```

## Manual Deployment Steps (if automated script fails)

1. **On VPS - Create virtual environment:**
```bash
cd /home/your_vps_username/shop_app
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

2. **Run migrations and collect static:**
```bash
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py tailwind build
```

3. **Setup Gunicorn service:**
```bash
sudo cp deployment/gunicorn.service /etc/systemd/system/wholeearn-shop.service
sudo systemctl daemon-reload
sudo systemctl enable wholeearn-shop
sudo systemctl start wholeearn-shop
sudo systemctl status wholeearn-shop
```

4. **Setup Nginx:**
```bash
sudo cp deployment/nginx.conf /etc/nginx/sites-available/shop.wholeshieldwellness.com
sudo ln -s /etc/nginx/sites-available/shop.wholeshieldwellness.com /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

## Post-Deployment

1. **Create Django superuser:**
```bash
cd /home/your_vps_username/shop_app/current
source ../venv/bin/activate
python manage.py createsuperuser
```

2. **Check service status:**
```bash
sudo systemctl status wholeearn-shop
sudo systemctl status nginx
```

3. **View logs:**
```bash
# Application logs
tail -f /home/your_vps_username/shop_app/logs/error.log
tail -f /home/your_vps_username/shop_app/logs/access.log

# Nginx logs
tail -f /var/log/nginx/shop.wholeshieldwellness.com-error.log
tail -f /var/log/nginx/shop.wholeshieldwellness.com-access.log
```

## Troubleshooting

**Gunicorn not starting:**
```bash
sudo journalctl -u wholeearn-shop -n 50
```

**Nginx errors:**
```bash
sudo nginx -t
sudo systemctl status nginx
```

**Permission issues:**
```bash
sudo chown -R your_vps_username:www-data /home/your_vps_username/shop_app
sudo chmod -R 755 /home/your_vps_username/shop_app
```

**Static files not loading:**
```bash
cd /home/your_vps_username/shop_app/current
source ../venv/bin/activate
python manage.py collectstatic --noinput
sudo systemctl restart wholeearn-shop
```

## Updating the Application

Simply run the deployment script again:
```bash
./deploy.sh
```

This will:
- Create a new release
- Deploy the latest code
- Run migrations
- Collect static files
- Restart services
- Keep the last 5 releases for rollback

## Rolling Back

To rollback to a previous release:
```bash
ssh your_vps_username@your_vps_ip
cd /home/your_vps_username/shop_app
ln -sfn releases/PREVIOUS_RELEASE_FOLDER current
sudo systemctl restart wholeearn-shop
```

## Monitoring

**Check disk usage:**
```bash
df -h
```

**Check memory usage:**
```bash
free -m
```

**Monitor application:**
```bash
htop
```

## Security Checklist

- ✅ SECRET_KEY is set to a strong random value
- ✅ DEBUG is set to False in production
- ✅ ALLOWED_HOSTS is configured correctly
- ✅ SSL certificate is installed
- ✅ Firewall is configured (ufw)
- ✅ Regular backups are scheduled
- ✅ Database credentials are secure
- ✅ .env file has proper permissions (600)

## Firewall Configuration

```bash
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

## Automated Backups (Optional)

Create a backup script:
```bash
nano /home/your_vps_username/backup.sh
```

Add:
```bash
#!/bin/bash
BACKUP_DIR="/home/your_vps_username/backups"
DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p $BACKUP_DIR
cd /home/your_vps_username/shop_app
tar -czf $BACKUP_DIR/backup_$DATE.tar.gz --exclude='venv' --exclude='*.pyc' .
find $BACKUP_DIR -type f -mtime +7 -delete
```

Make executable and add to crontab:
```bash
chmod +x /home/your_vps_username/backup.sh
crontab -e
# Add: 0 2 * * * /home/your_vps_username/backup.sh
```
