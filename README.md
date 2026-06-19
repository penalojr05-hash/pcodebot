# P Code Studio Bot

A comprehensive Discord bot for P Code Studio with support tickets, economy system, bot hosting, and more.

## Features

### 🎟️ Support Panel
- `/assistance panel` - Create support tickets for various services
- Automatic role assignment and channel creation
- Services include:
  - 👑 Leadership Support
  - 🤖 Discord Bot Development
  - 🎮 Roblox Game Development
  - 🎨 Graphic & UI Design
  - 🛠️ Discord Server Design
  - 💡 Custom Development Solutions
  - 🧑‍🏫 Learning & Training
  - 💬 General Support

### 🤖 Bot Management
- `/bot_log` - Log bots being developed with service and link tracking
- `/bot_host` - Host bots on P Code Bot system with uptime monitoring

### 💰 Economy System
- `/balance` - Check user balance and level
- `/daily` - Claim daily rewards
- `/transfer` - Send money to other users
- `/leaderboard` - View top 10 richest members

### 🎮 Fun Commands
- `/8ball` - Magic 8 ball for questions
- `/dice` - Roll a dice
- `/coinflip` - Flip a coin
- `/joke` - Get random jokes

### 📊 Additional Features
- Automatic welcome messages for new members
- Goodbye messages when members leave
- GitHub feed support
- SQLite database for persistence

## Setup Instructions

### 1. Clone the Repository
```bash
git clone https://github.com/penalojr05-hash/pcodebot.git
cd pcodebot
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Create .env File
Copy `.env.example` to `.env` and add your bot token:
```
DISCORD_TOKEN=your_actual_bot_token_here
```

### 4. Run the Bot
```bash
python main.py
```

## Configuration

All channel IDs and role IDs are hardcoded in `main.py`. To customize:

- `WELCOME_CHANNEL` = 1514684270596198594
- `SUPPORT_CHANNEL` = 1514684277764128800
- `GITHUB_CHANNEL` = 1514684267811180808
- `BOT_LOG_CHANNEL` = 1514684302502268929

## Database

The bot uses SQLite3 with the following tables:
- `economy` - User balance, level, and XP
- `bot_logs` - Tracked bots in development
- `bot_hosting` - Hosted bots with status monitoring
- `support_tickets` - Active support tickets

## Support Commands

All slash commands are available through Discord's slash command menu. Type `/` to see available commands.

## Security Notes

⚠️ **Never share your bot token!**
- Keep `.env` file local and never commit it to GitHub
- Always use environment variables for sensitive data
- The `.gitignore` file prevents accidental commits

## License

© P Code Studio | All Rights Reserved

## Support

For issues or questions, contact P Code Studio support through the bot's support panel.
