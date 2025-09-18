#!/bin/bash

# TerminalX Air-Gap Preparation Script
# Run this on an internet-connected machine to prepare everything for air-gapped deployment

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m'

# Configuration
DOMAIN="terminalx.yourdomain.com"  # UPDATE THIS!
EMAIL="admin@yourdomain.com"       # UPDATE THIS!
CERT_TYPE="self-signed"             # Options: letsencrypt, internal-ca, self-signed

# Functions
log() { echo -e "${BLUE}[INFO]${NC} $1"; }
success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }
header() { echo -e "${PURPLE}=============================================${NC}"; echo -e "${PURPLE}$1${NC}"; echo -e "${PURPLE}=============================================${NC}"; }

# Banner
show_banner() {
    clear
    header "  TerminalX Air-Gap Preparation  "
    echo ""
    echo "This script prepares everything needed for air-gapped deployment:"
    echo "  🐳 Downloads required Docker images"
    echo "  🔐 Generates/packages SSL certificates"
    echo "  📁 Creates deployment package"
    echo ""
    echo "Domain: $DOMAIN"
    echo "Email:  $EMAIL"
    echo "Cert:   $CERT_TYPE"
    echo ""
    echo -n "Continue? (y/N): "
    read confirm
    if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
        exit 0
    fi
}

# Check configuration
check_config() {
    if [[ "$DOMAIN" == "terminalx.yourdomain.com" ]] || [[ "$EMAIL" == "admin@yourdomain.com" ]]; then
        error "Please update DOMAIN and EMAIL variables in this script!"
        echo "Edit the script and change:"
        echo '  DOMAIN="terminalx.yourdomain.com"'
        echo '  EMAIL="admin@yourdomain.com"'
        exit 1
    fi
}

# Create working directory
setup_workspace() {
    header "Setting Up Workspace"
    
    WORKSPACE="terminalx-airgap-$(date +%Y%m%d_%H%M%S)"
    mkdir -p "$WORKSPACE"
    cd "$WORKSPACE"
    
    log "Created workspace: $WORKSPACE"
    success "Workspace ready"
}

# Download Docker images
download_docker_images() {
    header "Downloading Docker Images"
    
    IMAGES=(
        "terminalx:1.1.3.2d"
        "sftp-server:1.0.2.1"
        "nginx:alpine"
        "certbot/certbot:latest"
        "alpine:latest"
    )
    
    mkdir -p docker-images
    cd docker-images
    
    log "Downloading ${#IMAGES[@]} Docker images..."
    
    for image in "${IMAGES[@]}"; do
        log "Downloading $image..."
        docker pull "$image"
        
        # Save to tar file (safe filename)
        safe_name=$(echo "$image" | sed 's/[^a-zA-Z0-9._-]/_/g')
        docker save "$image" -o "${safe_name}.tar"
        
        # Compress to save space
        gzip "${safe_name}.tar"
        
        success "Saved: ${safe_name}.tar.gz"
    done
    
    # Create image loading script for air-gapped system
    cat > load-images.sh << 'EOF'
#!/bin/bash
echo "Loading Docker images for air-gapped deployment..."
for tar_file in *.tar.gz; do
    echo "Loading $tar_file..."
    gunzip -c "$tar_file" | docker load
done
echo "✅ All Docker images loaded successfully!"
echo ""
echo "Verify with: docker images"
EOF
    
    chmod +x load-images.sh
    
    # Create manifest
    echo "Docker Images for TerminalX Air-Gap Deployment" > manifest.txt
    echo "===============================================" >> manifest.txt
    echo "Generated: $(date)" >> manifest.txt
    echo "" >> manifest.txt
    echo "Images included:" >> manifest.txt
    for image in "${IMAGES[@]}"; do
        size=$(docker images --format "{{.Size}}" "$image" 2>/dev/null || echo "Unknown")
        echo "  - $image ($size)" >> manifest.txt
    done
    echo "" >> manifest.txt
    echo "Usage on air-gapped system:" >> manifest.txt
    echo "  1. Transfer entire docker-images/ directory" >> manifest.txt
    echo "  2. Run: ./load-images.sh" >> manifest.txt
    
    cd ..
    success "Docker images downloaded and packaged"
}

# Generate/package SSL certificates
handle_certificates() {
    header "SSL Certificate Preparation"
    
    mkdir -p certificates
    cd certificates
    
    case "$CERT_TYPE" in
        "letsencrypt")
            generate_letsencrypt_certs
            ;;
        "internal-ca")
            generate_internal_ca_certs
            ;;
        "self-signed")
            log "Self-signed certificates will be generated during deployment"
            create_self_signed_instructions
            ;;
        *)
            error "Unknown certificate type: $CERT_TYPE"
            exit 1
            ;;
    esac
    
    cd ..
}

# Generate Let's Encrypt certificates
generate_letsencrypt_certs() {
    log "Generating Let's Encrypt certificates for $DOMAIN..."
    
    # Check if certbot is available
    if ! command -v certbot &> /dev/null; then
        warning "Certbot not found. Installing via Docker..."
        
        # Use Docker certbot
        log "Using DNS challenge (requires manual DNS record creation)..."
        docker run -it --rm \
            -v "$(pwd)/letsencrypt:/etc/letsencrypt" \
            -v "$(pwd)/letsencrypt-lib:/var/lib/letsencrypt" \
            certbot/certbot certonly \
            --manual \
            --preferred-challenges dns \
            --email "$EMAIL" \
            --agree-tos \
            --no-eff-email \
            -d "$DOMAIN"
    else
        # Use system certbot
        log "Using DNS challenge (requires manual DNS record creation)..."
        sudo certbot certonly \
            --manual \
            --preferred-challenges dns \
            --email "$EMAIL" \
            --agree-tos \
            --no-eff-email \
            -d "$DOMAIN"
        
        # Copy certificates
        sudo cp -r /etc/letsencrypt/live /etc/letsencrypt/archive /etc/letsencrypt/renewal ./letsencrypt/
        sudo chown -R $(whoami):$(whoami) letsencrypt/
    fi
    
    # Package certificates
    tar -czf letsencrypt-certificates.tar.gz letsencrypt/
    
    # Create installation script
    cat > install-letsencrypt-certs.sh << EOF
#!/bin/bash
# Install Let's Encrypt certificates on air-gapped system

if [[ \$EUID -ne 0 ]]; then
    echo "This script must be run as root"
    echo "Please run: sudo \$0"
    exit 1
fi

echo "Installing Let's Encrypt certificates..."

# Extract certificates to system location
tar -xzf letsencrypt-certificates.tar.gz
cp -r letsencrypt/* /etc/letsencrypt/

# Create symlinks for nginx
mkdir -p /etc/ssl/{certs,private}
ln -sf /etc/letsencrypt/live/$DOMAIN/fullchain.pem /etc/ssl/certs/terminalx.crt
ln -sf /etc/letsencrypt/live/$DOMAIN/privkey.pem /etc/ssl/private/terminalx.key  
ln -sf /etc/letsencrypt/live/$DOMAIN/chain.pem /etc/ssl/certs/terminalx-chain.crt

# Set permissions
chmod 644 /etc/ssl/certs/terminalx*
chmod 600 /etc/ssl/private/terminalx*

echo "✅ Let's Encrypt certificates installed successfully!"
EOF
    
    chmod +x install-letsencrypt-certs.sh
    success "Let's Encrypt certificates prepared"
}

# Generate internal CA certificates
generate_internal_ca_certs() {
    log "Setting up internal CA certificate generation..."
    
    # Create CA generation script (to run if you have internal CA)
    cat > generate-internal-ca-certs.sh << EOF
#!/bin/bash
# Generate certificates using internal CA
# Update the paths below to point to your internal CA certificate and key

INTERNAL_CA_CERT="/path/to/your/internal-ca.crt"
INTERNAL_CA_KEY="/path/to/your/internal-ca.key"
DOMAIN="$DOMAIN"

if [[ ! -f "\$INTERNAL_CA_CERT" ]] || [[ ! -f "\$INTERNAL_CA_KEY" ]]; then
    echo "❌ Please update the INTERNAL_CA_CERT and INTERNAL_CA_KEY paths in this script"
    echo "Current paths:"
    echo "  CA Cert: \$INTERNAL_CA_CERT"
    echo "  CA Key:  \$INTERNAL_CA_KEY"
    exit 1
fi

echo "Generating certificate for \$DOMAIN using internal CA..."

# Generate private key
openssl genrsa -out terminalx.key 2048

# Generate certificate signing request
openssl req -new -key terminalx.key -out terminalx.csr \\
    -subj "/C=US/ST=State/L=City/O=YourOrg/CN=\$DOMAIN"

# Sign with internal CA
openssl x509 -req -in terminalx.csr \\
    -CA "\$INTERNAL_CA_CERT" \\
    -CAkey "\$INTERNAL_CA_KEY" \\
    -CAcreateserial \\
    -out terminalx.crt \\
    -days 365 \\
    -extensions v3_req

# Create certificate chain
cat terminalx.crt "\$INTERNAL_CA_CERT" > terminalx-chain.crt

# Package for transfer
tar -czf internal-ca-certs.tar.gz \\
    terminalx.crt terminalx.key terminalx-chain.crt

echo "✅ Internal CA certificates generated and packaged"
echo "📁 Transfer internal-ca-certs.tar.gz to air-gapped system"
EOF
    
    chmod +x generate-internal-ca-certs.sh
    
    # Create installation script
    cat > install-internal-ca-certs.sh << 'EOF'
#!/bin/bash
# Install internal CA certificates on air-gapped system

if [[ $EUID -ne 0 ]]; then
    echo "This script must be run as root"
    echo "Please run: sudo $0"
    exit 1
fi

if [[ ! -f "internal-ca-certs.tar.gz" ]]; then
    echo "❌ internal-ca-certs.tar.gz not found"
    echo "Please run generate-internal-ca-certs.sh first"
    exit 1
fi

echo "Installing internal CA certificates..."

# Extract certificates
tar -xzf internal-ca-certs.tar.gz

# Install to system locations
mkdir -p /etc/ssl/{certs,private}
cp terminalx.crt /etc/ssl/certs/
cp terminalx.key /etc/ssl/private/
cp terminalx-chain.crt /etc/ssl/certs/

# Set permissions
chmod 644 /etc/ssl/certs/terminalx*
chmod 600 /etc/ssl/private/terminalx*

echo "✅ Internal CA certificates installed successfully!"
EOF
    
    chmod +x install-internal-ca-certs.sh
    warning "Internal CA certificates require manual generation"
    log "Run generate-internal-ca-certs.sh after updating CA paths"
}

# Create self-signed certificate instructions
create_self_signed_instructions() {
    cat > self-signed-info.txt << EOF
Self-Signed Certificate Information
===================================

Self-signed certificates will be generated automatically during deployment.
No pre-generation is required.

However, clients will see certificate warnings. To avoid this:

1. Generate the certificate in advance:
   openssl req -x509 -newkey rsa:2048 \\
       -keyout terminalx.key \\
       -out terminalx.crt \\
       -days 365 -nodes \\
       -subj "/C=US/ST=State/L=City/O=TerminalX/CN=$DOMAIN"

2. Distribute terminalx.crt to client machines as a trusted root certificate

3. On air-gapped deployment, place certificates in:
   /etc/ssl/certs/terminalx.crt
   /etc/ssl/private/terminalx.key
   /etc/ssl/certs/terminalx-chain.crt (copy of terminalx.crt)
EOF
    
    success "Self-signed certificate instructions created"
}

# Create configuration files
create_config_files() {
    header "Creating Configuration Files"
    
    mkdir -p config
    cd config
    
    # Create simplified docker-compose template
    cat > docker-compose.yml << EOF
version: '3.8'

services:
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
      - TOKEN_SECRET=REPLACE_WITH_GENERATED_SECRET
      - TOKEN_TTL_SECONDS=120
    expose:
      - "8087"

  sftp-browser:
    image: sftp-server:1.0.2.1
    container_name: sftp-server
    restart: unless-stopped
    networks:
      - terminalx-network
    environment:
      - TOKEN_SECRET=REPLACE_WITH_GENERATED_SECRET
      - TOKEN_MAX_TTL_SECONDS=300
      - SESSION_TIMEOUT=600000
    expose:
      - "3000"

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
      - /etc/ssl/certs/terminalx.crt:/etc/ssl/certs/terminalx.crt:ro
      - /etc/ssl/private/terminalx.key:/etc/ssl/private/terminalx.key:ro
      - /etc/ssl/certs/terminalx-chain.crt:/etc/ssl/certs/terminalx-chain.crt:ro
      - ./logs/nginx:/var/log/nginx
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
EOF

    # Create nginx configuration templates
    mkdir -p nginx/conf.d
    
    # Main nginx config template (simplified for air-gap)
    cat > nginx/nginx.conf.template << 'EOF'
user nginx;
worker_processes ${WORKER_PROCESSES};
error_log /var/log/nginx/error.log warn;
pid /var/run/nginx.pid;

events {
    worker_connections ${WORKER_CONNECTIONS};
    use epoll;
    multi_accept on;
}

http {
    include /etc/nginx/mime.types;
    default_type application/octet-stream;

    log_format main '$remote_addr - $remote_user [$time_local] "$request" '
                    '$status $body_bytes_sent "$http_referer" '
                    '"$http_user_agent" "$http_x_forwarded_for"';

    access_log /var/log/nginx/access.log main;

    sendfile on;
    tcp_nopush on;
    tcp_nodelay on;
    keepalive_timeout 65;
    client_max_body_size ${CLIENT_MAX_BODY_SIZE};

    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_types text/plain text/css application/javascript application/json;

    limit_req_zone $binary_remote_addr zone=login:10m rate=${LOGIN_RATE_LIMIT};
    limit_req_zone $binary_remote_addr zone=api:10m rate=${API_RATE_LIMIT};

    map $http_upgrade $connection_upgrade {
        default upgrade;
        ''      close;
    }

    upstream terminalx_backend {
        server ${TERMINALX_BACKEND};
        keepalive 32;
    }

    upstream sftp_backend {
        server ${SFTP_BACKEND};
        keepalive 32;
    }

    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:10m;

    include /etc/nginx/conf.d/*.conf;
}
EOF

    # Site configuration template
    cat > nginx/conf.d/terminalx.conf.template << 'EOF'
# HTTP to HTTPS redirect
server {
    listen 80;
    server_name ${SERVER_NAME};
    
    location / {
        return 301 https://$server_name$request_uri;
    }
}

# HTTPS server
server {
    listen 443 ssl http2;
    server_name ${SERVER_NAME};
    
    ssl_certificate ${SSL_CERT_PATH};
    ssl_certificate_key ${SSL_KEY_PATH};
    
    add_header Strict-Transport-Security "max-age=31536000" always;
    
    location / {
        proxy_pass http://terminalx_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_read_timeout 86400;
        proxy_send_timeout 86400;
        proxy_buffering off;
    }
    
    location ~ ^/ws/ {
        proxy_pass http://terminalx_backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 3600;
        proxy_send_timeout 3600;
        proxy_buffering off;
    }
}

# Direct access servers
server {
    listen 8087;
    server_name _;
    
    location / {
        proxy_pass http://terminalx_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_buffering off;
    }
}

server {
    listen 3000;
    server_name _;
    
    location / {
        proxy_pass http://sftp_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_buffering off;
    }
}
EOF

    cd ..
    success "Configuration files created"
}

# Create deployment script for air-gapped system
create_deployment_script() {
    header "Creating Air-Gap Deployment Script"
    
    cat > deploy-airgapped.sh << 'EOF'
#!/bin/bash

# TerminalX Air-Gap Deployment Script
set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log() { echo -e "${BLUE}[INFO]${NC} $1"; }
success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }

echo "TerminalX Air-Gapped Deployment"
echo "==============================="

# Check if running as root
if [[ $EUID -ne 0 ]]; then
    error "This script must be run as root"
    echo "Please run: sudo $0"
    exit 1
fi

# Load Docker images
if [[ -d "docker-images" ]]; then
    log "Loading Docker images..."
    cd docker-images
    ./load-images.sh
    cd ..
    success "Docker images loaded"
else
    warning "docker-images directory not found, assuming images already loaded"
fi

# Install certificates if available
if [[ -f "certificates/install-letsencrypt-certs.sh" ]]; then
    log "Installing Let's Encrypt certificates..."
    cd certificates
    ./install-letsencrypt-certs.sh
    cd ..
elif [[ -f "certificates/install-internal-ca-certs.sh" ]]; then
    log "Installing internal CA certificates..."  
    cd certificates
    ./install-internal-ca-certs.sh
    cd ..
else
    log "No pre-generated certificates found, will use self-signed"
    
    # Generate self-signed certificates
    mkdir -p /etc/ssl/{certs,private}
    openssl req -x509 -newkey rsa:2048 \
        -keyout /etc/ssl/private/terminalx.key \
        -out /etc/ssl/certs/terminalx.crt \
        -days 365 -nodes \
        -subj "/C=US/ST=State/L=City/O=TerminalX/CN=terminalx.local"
    
    cp /etc/ssl/certs/terminalx.crt /etc/ssl/certs/terminalx-chain.crt
    chmod 644 /etc/ssl/certs/terminalx*
    chmod 600 /etc/ssl/private/terminalx*
    success "Self-signed certificates generated"
fi

# Setup configuration
log "Setting up configuration..."
cp -r config/* .
mkdir -p logs/nginx

# Generate random token secret
TOKEN_SECRET=$(openssl rand -hex 32)
sed -i "s/REPLACE_WITH_GENERATED_SECRET/$TOKEN_SECRET/g" docker-compose.yml

# Deploy services
log "Deploying services..."
docker-compose down 2>/dev/null || true
docker-compose up -d

# Wait for services
log "Waiting for services to start..."
sleep 20

# Test deployment
log "Testing deployment..."
SERVER_IP=$(ip route get 1 | sed -n 's/.*src \([0-9\.]*\).*/\1/p')

if curl -s --max-time 10 "http://$SERVER_IP:8087" > /dev/null; then
    success "TerminalX access working: http://$SERVER_IP:8087"
else
    warning "TerminalX access test failed"
fi

if curl -s --max-time 10 "http://$SERVER_IP:3000" > /dev/null; then
    success "SFTP access working: http://$SERVER_IP:3000"
else
    warning "SFTP access test failed"
fi

echo ""
success "✅ Air-gapped deployment complete!"
echo ""
echo "Access URLs:"
echo "  🖥️  TerminalX: http://$SERVER_IP:8087"
echo "  📁 SFTP:      http://$SERVER_IP:3000"
echo ""
echo "Management:"
echo "  📊 View logs:     docker-compose logs"
echo "  🔄 Restart:       docker-compose restart"
echo "  🛑 Stop services: docker-compose down"
EOF

    chmod +x deploy-airgapped.sh
    success "Air-gap deployment script created"
}

# Create final package
create_package() {
    header "Creating Final Package"
    
    # Create README
    cat > README.md << EOF
# TerminalX Air-Gap Deployment Package

Generated: $(date)
Domain: $DOMAIN
Certificate Type: $CERT_TYPE

## Contents

- \`docker-images/\` - Docker images and loading script
- \`certificates/\` - SSL certificate files and installation scripts
- \`config/\` - Docker Compose and nginx configuration templates  
- \`deploy-airgapped.sh\` - Main deployment script
- \`README.md\` - This file

## Deployment Instructions

1. Transfer this entire directory to your air-gapped system
2. Run: \`sudo ./deploy-airgapped.sh\`
3. Access TerminalX at: http://YOUR_SERVER_IP:8087

## Package Size

$(du -sh .)

## Verification

- Docker images: $(ls docker-images/*.tar.gz 2>/dev/null | wc -l) files
- Configuration: $(ls config/ | wc -l) files
- Certificates: $CERT_TYPE type

For support, see the included documentation files.
EOF

    # Create package checksum
    find . -type f -exec sha256sum {} \; | sort > CHECKSUMS.txt
    
    success "Final package created"
}

# Show final summary
show_summary() {
    header "🎉 Air-Gap Preparation Complete!"
    
    TOTAL_SIZE=$(du -sh . | cut -f1)
    IMAGE_COUNT=$(ls docker-images/*.tar.gz 2>/dev/null | wc -l)
    
    echo ""
    success "Air-gap deployment package ready!"
    echo ""
    echo "📦 Package Details:"
    echo "  📁 Location:      $(pwd)"
    echo "  💾 Total Size:    $TOTAL_SIZE"
    echo "  🐳 Docker Images: $IMAGE_COUNT files"
    echo "  🔐 Certificates:  $CERT_TYPE"
    echo "  🎯 Target Domain: $DOMAIN"
    echo ""
    echo "📋 Transfer Instructions:"
    echo "  1. Copy entire directory to air-gapped system"
    echo "  2. Run: sudo ./deploy-airgapped.sh"
    echo "  3. Access at: http://SERVER_IP:8087"
    echo ""
    echo "📁 Package Contents:"
    ls -la
    echo ""
    success "Ready for air-gapped deployment! 🚀"
}

# Main execution
main() {
    show_banner
    check_config
    setup_workspace
    download_docker_images
    handle_certificates  
    create_config_files
    create_deployment_script
    create_package
    show_summary
}

# Run main function
main "$@"