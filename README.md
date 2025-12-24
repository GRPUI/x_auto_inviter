# X Community Auto-Inviter

A Python-based tool to automatically invite users to X (formerly Twitter) communities using multiple accounts and Redis-based task locking for distributed processing.

## Features

- **Multi-token support**: Use multiple X accounts to send invitations concurrently
- **Distributed processing**: Redis-based task locking prevents duplicate invitations
- **Error handling**: Robust error handling and logging for failed operations
- **Parallel workers**: Configurable number of concurrent workers for faster processing
- **Duplicate prevention**: Tracks already invited users to prevent redundant invites
- **Stealth browsing**: Uses Camoufox for human-like browser automation

## Requirements

- Python 3.8+
- Redis server
- X tokens (authentication cookies)
- List of usernames to invite

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/x_invite_auto.git
cd x_invite_auto
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Start Redis server:
```bash
redis-server
```

## Configuration

### 1. Prepare Your Files

**Tokens File** (`tokens.txt`):
```
your_x_token_1_here
your_x_token_2_here
your_x_token_3_here
```

**Users File** (`users.txt`):
```
username1
username2
username3
```

### 2. Run the Script

```bash
python main.py -t tokens.txt -u users.txt [OPTIONS]
```

## Command Line Arguments

| Argument | Short | Description | Default |
|----------|-------|-------------|---------|
| `--tokens` | `-t` | Path to tokens file (required) | |
| `--users` | `-u` | Path to users file (required) | |
| `--community` | `-c` | Community URL | `https://x.com/` |
| `--workers` | `-w` | Number of parallel workers | `3` |
| `--redis` | `-r` | Redis URL | `redis://localhost:6379` |

## Examples

### Basic Usage
```bash
python main.py -t tokens.txt -u users.txt
```

### Custom Community and Workers
```bash
python main.py -t tokens.txt -u users.txt -c "https://x.com/i/communities/1996945882479026553/" -w 5
```

### Remote Redis
```bash
python main.py -t tokens.txt -u users.txt -r "redis://your-redis-server:6379"
```

## How It Works

1. **Token Processing**: Each worker uses a different X token to send invitations
2. **Task Locking**: Redis locks prevent multiple workers from inviting the same user
3. **Duplicate Prevention**: Already invited users are tracked in Redis
4. **Error Handling**: Failed invitations are logged without stopping the entire process
5. **Statistics**: At the end, reports total users invited vs. total users

## Architecture

- `main.py`: Core logic for invitation automation
- `x_token_login.py`: Handles X token authentication
- `read_files.py`: Utility for reading tokens and users from files
- `task_locking/in_redis.py`: Redis-based distributed locking system
- `requirements.txt`: Python dependencies

## Security Notes

- Store your tokens securely and never commit them to version control
- Use a dedicated Redis instance for production use
- Monitor your Redis usage for memory consumption

## Troubleshooting

### Common Issues

1. **Redis Connection Error**
   - Ensure Redis server is running
   - Check Redis URL configuration

2. **Authentication Failed**
   - Verify X tokens are valid and not expired
   - Check tokens file format

3. **Rate Limiting**
   - Reduce number of workers
   - Add delays between invitations

### Logs

The tool uses Loguru for logging. Check console output for:
- Worker progress
- Success/failure messages
- Statistics at completion

## License

[Your License Here]

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## Disclaimer

This tool is for educational purposes only. Use responsibly and comply with X's Terms of Service. Do not use for spam or harassment.