# AI Battle Bots with MCP

## Document Source
- [LangChain](https://docs.langchain.com/oss/python/langchain/overview)
- [AnythingLLM](https://docs.anythingllm.com/introduction)

## DVL Soucre
- [DVL](https://www.vulnhub.com/series/damn-vulnerable-linux-dvl,1/)
- [DVL Setup](https://github.com/alyssarusk/ai-battle-bots/blob/main/DVL.md)
## Setup
### 1. mcp-kali-server
MCP bridging Kali VM and Agents [Github](https://github.com/Wh0am123/MCP-Kali-Server).

#### 1.1 Setting up on Kali VM

1. Download and import Kali VM from [offical website](https://www.kali.org/get-kali/#kali-virtual-machines)
    - Extract zip to desired location
    - In VirtualBox, click **Add** to import VM
    - Change network setting to **Bridged Adapter**
    - Open VM, username/password: kali
2. In Kali VM, clone MCP Server
    ```
    git clone https://github.com/Wh0am123/MCP-Kali-Server.git
    ```
3. Start Server
    ```
    python MCP-Kali-Server/kali_server.py
    ```

#### 1.2 Setting up on Host Machine 

1. Clone the repo & install requirements
    ```
    git clone https://github.com/Wh0am123/MCP-Kali-Server.git
    cd MCP-Kali-Server
    python3 -m venv venv

    # For Mac or Linux
    source venv/bin/activate

    # For Windows
    .\venv\Scripts\activate.bat

    pip install requests fastmcp
    ```

2. Fix logging errors in `mcp_server.py` file by changing:

    ```python
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout) # This line needs changing
        ]
    )
    ```

    To:
    ```python
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.StreamHandler(sys.stderr) # Change to this
        ]
    )
    ```

3. Start server
    ```
    python kali_server.py
    ```

### 2. redstack-vault
#### 2.1 Start Server
Navigate to redstack-vault/.mcp-server
Run
```
./start.sh
```

### 3. Project Installation
```
pip install -r requirements.txt
```
**Packages**
- langchain
- openailangchain_openai - OpenAI-compatible models
- mcp - connection to MCP servers
- .env - manage env variables
- requests - needed to connect to APIs (AnythingLLM)
- psycopg2 - connecting to db

## Repo Folders
### agents 
Python files for agents created using Langchain.

Currently containing agent:
- Orchestrator

*get_workspaces.py can be used to find AnythingLLM workplace slugs*

### config_files
json files needed to connect the Kali MCP to the LLM.

Currently containing config file for:
- AnythingLLM

### docs/weekly_updates

Weekly progress reports.



