"# 9_order_bot" 
<!-- Exact Guide to Deploy Apps on GCP VM
This guide is tailored for deploying Python/Docker-based apps like your Telegram bot on a GCP VM, based on the chat's lessons. It's designed for a Windows local machine and Debian 12 VM. Assume you have the Google Cloud SDK installed locally (download from cloud.google.com/sdk). The guide is divided into phases with bullet flows for clarity.

Phase 1: Preparation on Local Machine (Windows)

Gather required assets:

App code: app.py (your bot script).
Dependencies: requirements.txt (e.g., openai, python-telegram-bot[callback-data], gspread, oauth2client, tenacity).
Dockerfile: Your provided Dockerfile.
Config files: credentials.json (Google Sheets service account JSON), customers.json (JSON array of customers).
EVs: Note your Telegram bot token, OpenAI API key.


Validate files locally:

Open credentials.json and customers.json in VS Code or a JSON linter (e.g., jsonlint.com) to ensure valid JSON.
Test bot token and OpenAI key (e.g., curl to Telegram API: curl https://api.telegram.org/bot<token>/getMe).


Install tools:

Google Cloud SDK for gcloud.
Git Bash or PowerShell for SCP/curl compatibility.
Optional: WinSCP for GUI file upload.




Phase 2: Create and Configure the VM in GCP Console

Log in to console.cloud.google.com with your account (e.g., borissolomonia@gmail.com).
Select or create the project:

Project ID: nine-tones-bots-2025-468320 (or your own).


Create the VM:

Go to Compute Engine > VM instances > Create instance.
Set name: e.g., telegram-bot-vm (or use instance-20250808-061254).
Region/Zone: us-central1-c (low latency for US).
Machine type: e2-micro (free tier) or e2-small for testing.
Boot disk: Debian 12 Bookworm, 10-20 GB persistent disk.
Firewall: Allow SSH (default port 22).
Advanced: No HTTP/HTTPS needed (bot uses outbound only).


Note VM details:

External IP: e.g., 34.69.127.48 (ephemeral or static).
Username: borissolomonia.


Enable APIs (if needed for Sheets/OpenAI):

Search for "API Library" > Enable "Google Sheets API" for your project.




Phase 3: SSH into the VM and Setup Base Environment

From local Windows:

Run: gcloud compute ssh borissolomonia@instance-20250808-061254 --zone us-central1-c --project nine-tones-bots-2025-468320.
If errors:

Check project: gcloud config set project nine-tones-bots-2025-468320.
Re-authenticate: gcloud auth login.
Alternative: Use GCP Console SSH (VM instances > SSH button).




Update system:

sudo apt update && sudo apt upgrade -y.


Install Docker:

sudo apt install ca-certificates curl gnupg lsb-release -y.
sudo mkdir -p /etc/apt/keyrings.
curl -fsSL https://download.docker.com/linux/debian/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg.
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian bookworm stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null.
sudo apt update.
sudo apt install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin -y.
Add user to group: sudo groupadd docker; sudo usermod -aG docker $USER; newgrp docker.
Verify: docker run hello-world.




Phase 4: Upload Files to the VM

From local Windows (in the app directory, e.g., C:\Users\boris\D_disc_Boris\BORIS\stuff\9_TONES\APPS\telegram_bot\payment-bot):

Run: gcloud compute scp app.py requirements.txt Dockerfile credentials.json customers.json borissolomonia@instance-20250808-061254:/home/borissolomonia --zone us-central1-c --project nine-tones-bots-2025-468320.
If errors:

Use explicit path: /home/borissolomonia.
Alternative: WinSCP to IP 34.69.127.48, username borissolomonia.




In VM:

Verify: ls -l (should show all files).
Validate JSON: sudo apt install jq -y; cat credentials.json | jq .; cat customers.json | jq ..




Phase 5: Build and Run the Docker Container

In VM (navigate to /home/borissolomonia if needed: cd /home/borissolomonia):

Build image: docker build -t payment-bot . (or order-bot).
Run container:

docker run -d --restart=always -e ORDER_BOT_TOKEN="your-bot-token" -e OPENAI_API_KEY="your-openai-key" -e SHEETS_CREDS="$(cat credentials.json)" -e CUSTOMERS_JSON="$(cat customers.json)" --name order-bot-container order-bot.


Verify: docker ps (should show 'Up').
Logs: docker logs -f payment-bot-container (look for "Starting Order Bot polling...").


Test bot:

Send Telegram message (e.g., "შპს მაგსი 20 საქონლის ბარკალი").
Check logs for processing.




Phase 6: Persistence and Monitoring

Add VM startup script (GCP Console > VM > Edit > Metadata):

Key: startup-script.
Value: #!/bin/bash\ndocker start payment-bot-container.


Monitor:

Container: docker stats.
VM: GCP Console > Monitoring.
Logs: docker logs payment-bot-container.


Scale/Update:

Stop container: docker stop payment-bot-container.
Rebuild: Edit files, docker build -t payment-bot ., re-run.




Phase 7: Cleanup and Security

Secure EVs: Don't hardcode; use GCP Secrets Manager if scaling.
Cleanup: docker rm -f payment-bot-container; docker rmi payment-bot.
Costs: Monitor in GCP Billing (e2-micro is free tier).



Network Diagram Visualization
The following is a text-based network diagram visualizing the deployment flow and connections (generated via code execution for clarity):
textUser's Local Machine (Windows)
  |
  | SCP/SSH (gcloud or direct)
  v
GCP Cloud (Project: nine-tones-bots-2025-468320)
  |
  | VM Instance (instance-20250808-061254, Debian 12)
  | External IP: 34.69.127.48
  | Zone: us-central1-c
  |
  | Docker Installed
  | App Files Uploaded (app.py, Dockerfile, etc.)
  v
Docker Container (payment-bot-container)
  - Runs Python Telegram Bot
  - EVs: ORDER_BOT_TOKEN, OPENAI_API_KEY, SHEETS_CREDS, CUSTOMERS_JSON
  |
  | Outbound Connections:
  | - Telegram API (api.telegram.org)
  | - OpenAI API (api.openai.com)
  | - Google Sheets API (sheets.googleapis.com)
  v
External Services
- Telegram (Inbound messages to bot)
- OpenAI (For parsing orders)
- Google Sheets (For recording orders) -->

---

<!-- როდესაც არსებული აპია GCP VM ზე უკვე გატანილი და მისი ცვლილებაა საჭირო, ამისთვის ჯერ უნდა გაითიშოს და წაიშალოს არსებული კონტეინერი:

docker stop payment-bot-container
docker rm payment-bot-container

შემდეგ vm ზე განთავსდეს ფაილები ლოკალიდან

gcloud compute scp orderapp.py requirements.txt Dockerfile  borissolomonia@instance-20250808-061254:/home/borissolomonia --zone us-central1-c --project nine-tones-bots-2025-468320

შემდეგ docker build -t სახელი .

შემდეგ docker run -it --name payment-bot-container -e ORDER_BOT_TOKEN="your_token" -e OPENAI_API_KEY="your_api_key" -e SHEETS_CREDS="your_credentials.json" -e CUSTOMERS_JSON="your_customers.json" -p 8080:8080 --restart=always -d სახელი -->