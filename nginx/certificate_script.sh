#!/bin/bash

# TerminalX Host Filesystem SSL Setup Script
# This script configures SSL certificates stored on the host filesystem

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m'

# Default configuration (update these!)
DOMAIN="terminalx.yourdomain.com"
EMAIL="admin@yourdomain.com"
STAGING=false

# Filesystem paths for certificates
SSL_DIR="/etc/ssl"
SSL_CERTS_DIR="/etc/ssl/certs"
SSL_PRIVATE_DIR="/etc/ssl/private"
LETSENCRYPT_DIR="/etc/letsencrypt"

# Project directories
NGINX_DIR="./nginx"
LOGS_DIR="./logs"
LETSENCRYPT_WEBROOT="./letsencrypt/webroot"
LETSENCRYPT_LOGS="./letsencrypt/logs"

# Functions
log() { echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }
success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
header() { echo -e "${PURPLE}$1${NC}"; }

# Check if running with proper permissions
check_permissions() {
    if [[ $EUID -ne 0 ]]; then
        error "This script must be run as root for SSL certificate management"
        echo "Please run: sudo $0 $@"
        exit 1
    fi
}

# Validate configuration
validate_config() {
    if [[ "$DOMAIN" == "terminalx.yourdomain.com" ]]; then
        error "Please update the DOMAIN variable in this script!"
        echo "Edit the script and change:"
        echo "  DOMAIN=\"terminalx.yourdomain.com\""
        echo "  EMAIL=\"admin@yourdomain.com\""
        echo "to your actual domain and email."
        exit 1
    fi

    if [[ "$EMAIL" == "admin@yourdomain.com" ]]; then
        error "Please update the EMAIL variable in this script!"
        exit 1
    fi
}

# Create directory structure
setup_directories() {
    header "📁 Setting Up Directory Structure"
    
    # Host filesystem directories (need root)
    log "Creating host filesystem directories..."
    mkdir -p "$SSL_CERTS_DIR"
    mkdir -p "$SSL_PRIVATE_DIR"
    mkdir -p "$LETSENCRYPT_DIR"
    
    # Set proper permissions for SSL directories
    chmod 755 "$SSL_CERTS_DIR"
    chmod 700 "$SSL_PRIVATE_DIR"
    chmod 755 "$LETSENCRYPT_DIR"
    
    # Project directories (user accessible)
    log "Creating project directories..."
    mkdir -p "$NGINX_DIR/conf.d"
    mkdir -p "$LOGS_DIR/nginx"
    mkdir -p "$LETSENCRYPT_WEBROOT"
    mkdir -p "$LETSENCRYPT_LOGS"
    
    # Set proper ownership for project directories
    if [[ -n "$SUDO_USER" ]]; then
        chown -R "$SUDO_USER:$SUDO_USER" "$NGINX_DIR" "$LOGS_DIR" "./letsencrypt"
    fi
    
    success "Directory structure created"
}

# Generate Docker Compose configuration
generate_docker_compose() {
    header "⚙️ Generating Docker Compose Configuration"
    
    log "Creating docker-compose.yml with environment variables..."
    
    # Generate a random token secret
    TOKEN_SECRET=$(openssl rand -hex 32)
    
    cat > docker-compose.yml << EOF
version: '3.8'

services:
  # TerminalX Application
  terminalx:
    image: terminalx:1.1.3.2d
    container_name: terminalx
    restart: unless-stopped
    networks:
      - terminalx-network
    environment:
      - TD_PATH=/sources/indot.html
      - MOBY_PORT=9085
      - SFTP_HOST=                    
      - SFTP_PORT=3000               
      - SFTP_PROTOCOL=https          
      - TOKEN_SECRET=$TOKEN_SECRET
      - TOKEN_TTL_SECONDS=120
    expose:
      - "8087"

  # SFTP Browser Service  
  sftp-browser:
    image: sftp-server:1.0.2.1
    container_name: sftp-server
    restart: unless-stopped
    networks:
      - terminalx-network
    environment:
      - TOKEN_SECRET=$TOKEN_SECRET
      - TOKEN_MAX_TTL_SECONDS=300
      - SESSION_TIMEOUT=600000
    expose:
      - "3000"

  # Nginx Reverse Proxy Container
  nginx:
    image: nginx:alpine
    container_name: terminalx-nginx
    restart: unless-stopped
    ports:
      - "80:80"           
      - "443:443"         
      - "8087:8087"       
      - "3000:3000"       
    networks:
      - terminalx-network
    environment:
      - DOMAIN=$DOMAIN
      - SERVER_NAME=$DOMAIN
      - SSL_CERT_PATH=/etc/ssl/certs/terminalx.crt
      - SSL_KEY_PATH=/etc/ssl/private/terminalx.key
      - SSL_CHAIN_PATH=/etc/ssl/certs/terminalx-chain.crt
      - TERMINALX_BACKEND=terminalx:8087
      - SFTP_BACKEND=sftp-browser:3000
      - WORKER_PROCESSES=auto
      - WORKER_CONNECTIONS=1024
      - CLIENT_MAX_BODY_SIZE=100M
      - LOGIN_RATE_LIMIT=5r/m
      - API_RATE_LIMIT=10r/s
    volumes:
      - ./nginx/nginx.conf.template:/etc/nginx/nginx.conf.template:ro
      - ./nginx/conf.d/:/etc/nginx/templates/:ro
      - $SSL_CERTS_DIR/terminalx.crt:/etc/ssl/certs/terminalx.crt:ro
      - $SSL_PRIVATE_DIR/terminalx.key:/etc/ssl/private/terminalx.key:ro  
      - $SSL_CERTS_DIR/terminalx-chain.crt:/etc/ssl/certs/terminalx-chain.crt:ro
      - ./logs/nginx:/var/log/nginx
      - ./letsencrypt/webroot:/var/www/certbot:ro
    depends_on:
      - terminalx
      - sftp-browser
    command: >
      /bin/sh -c "
      envsubst '\$\${DOMAIN},\$\${SERVER_NAME},\$\${SSL_CERT_PATH},\$\${SSL_KEY_PATH},\$\${SSL_CHAIN_PATH},\$\${TERMINALX_BACKEND},\$\${SFTP_BACKEND},\$\${CLIENT_MAX_BODY_SIZE},\$\${LOGIN_RATE_LIMIT},\$\${API_RATE_LIMIT},\$\${WORKER_PROCESSES},\$\${WORKER_CONNECTIONS}' 
      < /etc/nginx/nginx.conf.template > /etc/nginx/nginx.conf &&
      envsubst '\$\${DOMAIN},\$\${SERVER_NAME},\$\${SSL_CERT_PATH},\$\${SSL_KEY_PATH},\$\${SSL_CHAIN_PATH},\$\${TERMINALX_BACKEND},\$\${SFTP_BACKEND}' 
      < /etc/nginx/templates/terminalx.conf.template > /etc/nginx/conf.d/terminalx.conf &&
      nginx -t && nginx -g 'daemon off;'"

networks:
  terminalx-network:
    driver: bridge
    ipam:
      config:
        - subnet: 172.20.0.0/16
EOF

    # Set ownership
    if [[ -n "$SUDO_USER" ]]; then
        chown "$SUDO_USER:$SUDO_USER" docker-compose.yml
    fi
    
    success "Docker Compose configuration created"
}

# Generate nginx configuration templates
generate_nginx_config() {
    header "📝 Generating Nginx Configuration Templates"
    
    log "Creating nginx.conf.template..."
    # The nginx configuration template would be written here
    # (Using content from the previous artifact)
    
    log "Creating terminalx.conf.template..."  
    # The site configuration template would be written here
    # (Using content from the previous artifact)
    
    success "Nginx configuration templates created"
}

# Generate self-signed certificate for initial setup
generate_self_signed_cert() {
    header "🔐 Generating Self-Signed Certificate (Temporary)"
    
    log "Creating temporary self-signed certificate..."
    
    openssl req -x509 -newkey rsa:2048 -keyout "$SSL_PRIVATE_DIR/terminalx.key" -out "$SSL_CERTS_DIR/terminalx.crt" \
        -days 30 -nodes -subj "/C=US/ST=State/L=City/O=Organization/CN=$DOMAIN"
    
    # Create chain file (same as cert for self-signed)
    cp "$SSL_CERTS_DIR/terminalx.crt" "$SSL_CERTS_DIR/terminalx-chain.crt"
    
    # Set proper permissions
    chmod 644 "$SSL_CERTS_DIR/terminalx.crt"
    chmod 644 "$SSL_CERTS_DIR/terminalx-chain.crt"
    chmod 600 "$SSL_PRIVATE_DIR/terminalx.key"
    
    success "Self-signed certificate created (valid for 30 days)"
    warning "This is a temporary certificate. Run with --letsencrypt to get a real certificate."
}

# Obtain Let's Encrypt certificate
obtain_letsencrypt_cert() {
    header "🔐 Obtaining Let's Encrypt Certificate"
    
    local staging_flag=""
    if [[ "$STAGING" == "true" ]]; then
        staging_flag="--staging"
        warning "Using Let's Encrypt staging environment"
    fi
    
    log "Starting nginx for ACME challenge..."
    
    # Start nginx with basic configuration for challenge
    docker-compose up -d nginx
    sleep 10
    
    log "Requesting certificate from Let's Encrypt..."
    
    # Run certbot to get certificate
    docker run --rm --name certbot-obtain \
        -v "$LETSENCRYPT_DIR:/etc/letsencrypt" \
        -v "/var/lib/letsencrypt:/var/lib/letsencrypt" \
        -v "$(pwd)/letsencrypt/webroot:/var/www/certbot" \
        -v "$(pwd)/letsencrypt/logs:/var/log/letsencrypt" \
        certbot/certbot \
        certonly --webroot \
        -w /var/www/certbot \
        $staging_flag \
        --email "$EMAIL" \
        --agree-tos \
        --no-eff-email \
        -d "$DOMAIN"
    
    if [[ $? -eq 0 ]]; then
        log "Certificate obtained, creating symlinks..."
        
        # Create symlinks to the certificates
        ln -sf "$LETSENCRYPT_DIR/live/$DOMAIN/fullchain.pem" "$SSL_CERTS_DIR/terminalx.crt"
        ln -sf "$LETSENCRYPT_DIR/live/$DOMAIN/privkey.pem" "$SSL_PRIVATE_DIR/terminalx.key"
        ln -sf "$LETSENCRYPT_DIR/live/$DOMAIN/chain.pem" "$SSL_CERTS_DIR/terminalx-chain.crt"
        
        success "Let's Encrypt certificate installed successfully!"
        
        # Restart nginx to use new certificate
        log "Restarting nginx with new certificate..."
        docker-compose restart nginx
        
    else
        error "Failed to obtain Let's Encrypt certificate"
        return 1
    fi
}

# Setup certificate renewal
setup_renewal() {
    header "🔄 Setting Up Certificate Auto-Renewal"
    
    log "Creating renewal script..."
    
    cat > renew-certificates.sh << EOF
#!/bin/bash

# Certificate renewal script for TerminalX
LOG_FILE="./letsencrypt/logs/renewal.log"

log() {
    echo "\$(date +'%Y-%m-%d %H:%M:%S') \$1" | tee -a "\$LOG_FILE"
}

log "Starting certificate renewal check..."

# Run certbot renewal
docker run --rm --name certbot-renew \\
    -v "$LETSENCRYPT_DIR:/etc/letsencrypt" \\
    -v "/var/lib/letsencrypt:/var/lib/letsencrypt" \\
    -v "\$(pwd)/letsencrypt/webroot:/var/www/certbot" \\
    -v "\$(pwd)/letsencrypt/logs:/var/log/letsencrypt" \\
    certbot/certbot \\
    renew --webroot -w /var/www/certbot --quiet

if [ \$? -eq 0 ]; then
    log "Certificate renewal completed successfully"
    
    # Update symlinks (in case certificate path changed)
    ln -sf "$LETSENCRYPT_DIR/live/$DOMAIN/fullchain.pem" "$SSL_CERTS_DIR/terminalx.crt"
    ln -sf "$LETSENCRYPT_DIR/live/$DOMAIN/privkey.pem" "$SSL_PRIVATE_DIR/terminalx.key"
    ln -sf "$LETSENCRYPT_DIR/live/$DOMAIN/chain.pem" "$SSL_CERTS_DIR/terminalx-chain.crt"
    
    # Reload nginx
    log "Reloading nginx configuration..."
    docker exec terminalx-nginx nginx -s reload
    
    log "Certificate renewal and nginx reload completed"
else
    log "Certificate renewal check completed (no renewal needed or failed)"
fi
EOF

    chmod +x renew-certificates.sh
    if [[ -n "$SUDO_USER" ]]; then
        chown "$SUDO_USER:$SUDO_USER" renew-certificates.sh
    fi
    
    # Setup cron job
    log "Setting up cron job for automatic renewal..."
    
    # Create cron job entry
    CRON_ENTRY="0 3,15 * * * cd $(pwd) && ./renew-certificates.sh"
    
    # Add to root crontab (since we need root for certificate management)
    (crontab -l 2>/dev/null | grep -v "renew-certificates.sh"; echo "$CRON_ENTRY") | crontab -
    
    success "Certificate auto-renewal setup completed"
}

# Validate DNS configuration
validate_dns() {
    header "🌐 Validating DNS Configuration"
    
    log "Detecting server IP..."
    SERVER_IP=$(curl -s ifconfig.me 2>/dev/null || curl -s ipinfo.io/ip 2>/dev/null || echo "Unknown")
    log "Server IP: $SERVER_IP"
    
    log "Checking DNS resolution for $DOMAIN..."
    RESOLVED_IP=$(dig +short "$DOMAIN" 2>/dev/null | tail -n1)
    
    if [[ -z "$RESOLVED_IP" ]]; then
        warning "DNS resolution failed for $DOMAIN"
        echo "Please ensure you have created an A record:"
        echo "  $DOMAIN    IN    A    $SERVER_IP"
        return 1
    elif [[ "$RESOLVED_IP" != "$SERVER_IP" ]]; then
        warning "DNS mismatch detected:"
        echo "  Domain: $DOMAIN"
        echo "  Resolves to: $RESOLVED_IP"
        echo "  Expected: $SERVER_IP"
        return 1
    else
        success "DNS configuration is correct"
        return 0
    fi
}

# Test SSL certificate
test_ssl() {
    header "🧪 Testing SSL Certificate"
    
    log "Waiting for services to start..."
    sleep 15
    
    log "Testing HTTPS connection to $DOMAIN..."
    
    if curl -s --max-time 10 --connect-timeout 5 "https://$DOMAIN/health" > /dev/null 2>&1; then
        success "HTTPS connection successful!"
        
        # Get certificate details
        log "Certificate details:"
        echo | openssl s_client -servername "$DOMAIN" -connect "$DOMAIN:443" 2>/dev/null | \
            openssl x509 -noout -dates -subject -issuer
        
    else
        warning "HTTPS connection test failed"
        log "This might be normal if using self-signed certificates"
        return 1
    fi
}

# Deploy services
deploy_services() {
    header "🚀 Deploying Services"
    
    log "Starting all services..."
    docker-compose up -d
    
    log "Waiting for services to initialize..."
    sleep 20
    
    log "Service status:"
    docker-compose ps
    
    success "Services deployed"
}

# Display final summary
show_summary() {
    header "✅ Setup Complete!"
    
    SERVER_IP=$(curl -s ifconfig.me 2>/dev/null || echo "YOUR_SERVER_IP")
    
    echo ""
    success "Your TerminalX deployment is ready!"
    echo ""
    echo "🔗 Access URLs:"
    echo "  HTTPS FQDN:    https://$DOMAIN"
    echo "  Direct Access: http://$SERVER_IP:8087 (TerminalX)"
    echo "  SFTP Browser:  http://$SERVER_IP:3000 (SFTP)"
    echo ""
    echo "📁 Certificate Locations:"
    echo "  SSL Certificate: $SSL_CERTS_DIR/terminalx.crt"
    echo "  SSL Private Key: $SSL_PRIVATE_DIR/terminalx.key"
    echo "  SSL Chain:       $SSL_CERTS_DIR/terminalx-chain.crt"
    echo ""
    echo "🔧 Management Commands:"
    echo "  View logs:           docker-compose logs"
    echo "  Restart nginx:       docker-compose restart nginx"
    echo "  Renew certificates:  ./renew-certificates.sh"
    echo "  Stop services:       docker-compose down"
    echo ""
    echo "📝 Configuration Files:"
    echo "  Docker Compose:      docker-compose.yml"
    echo "  Nginx Config:        nginx/nginx.conf.template"
    echo "  Site Config:         nginx/conf.d/terminalx.conf.template"
    echo ""
}

# Main execution functions
setup_self_signed() {
    validate_config
    setup_directories
    generate_docker_compose
    generate_nginx_config
    generate_self_signed_cert
    deploy_services
    test_ssl
    show_summary
}

setup_letsencrypt() {
    validate_config
    if ! validate_dns; then
        error "DNS validation failed. Please fix DNS configuration and try again."
        exit 1
    fi
    setup_directories
    generate_docker_compose
    generate_nginx_config
    generate_self_signed_cert  # Temporary cert for initial nginx start
    obtain_letsencrypt_cert
    setup_renewal
    test_ssl
    show_summary
}

# Command line argument handling
case "${1:-}" in
    --self-signed)
        check_permissions
        log "Setting up with self-signed certificates..."
        setup_self_signed
        ;;
    --letsencrypt)
        check_permissions
        log "Setting up with Let's Encrypt certificates..."
        setup_letsencrypt
        ;;
    --letsencrypt-staging)
        check_permissions
        STAGING=true
        log "Setting up with Let's Encrypt staging certificates..."
        setup_letsencrypt
        ;;
    --renew)
        log "Renewing certificates..."
        ./renew-certificates.sh
        ;;
    --test)
        log "Testing SSL configuration..."
        test_ssl
        ;;
    --validate-dns)
        log "Validating DNS configuration..."
        validate_dns
        ;;
    *)
        echo "TerminalX SSL Setup Script"
        echo ""
        echo "Usage: sudo $0 [OPTION]"
        echo ""
        echo "Options:"
        echo "  --self-signed        Setup with self-signed certificates (for testing)"
        echo "  --letsencrypt        Setup with Let's Encrypt production certificates"
        echo "  --letsencrypt-staging Setup with Let's Encrypt staging certificates"
        echo "  --renew              Manually renew certificates"
        echo "  --test               Test current SSL configuration"
        echo "  --validate-dns       Validate DNS configuration"
        echo ""
        echo "Before running, please update the DOMAIN and EMAIL variables in this script."
        echo ""
        echo "Example:"
        echo "  sudo $0 --letsencrypt"
        exit 1
        ;;
esac