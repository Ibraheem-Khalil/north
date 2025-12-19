"""
NORTH - Multi-Agent AI System
Main entry point for the application
"""

import warnings
# Suppress protobuf version warnings
warnings.filterwarnings('ignore', category=UserWarning, message='.*Protobuf gencode version.*')

import os
import sys
import logging
from dotenv import load_dotenv

# Add src directory to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

# Import the main orchestrator
from src.core.north_orchestrator import NORTH

# Enable LangSmith tracing for debugging (opt-in via env flag)
if os.getenv("ENABLE_LS_TRACING", "false").lower() == "true":
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_PROJECT"] = os.getenv("LANGCHAIN_PROJECT", "NORTH-MAIN")

# Fix Windows console encoding for Unicode
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()  # Console output only, no file logging
    ]
)
logger = logging.getLogger(__name__)


def interactive_mode(north):
    """Run NORTH in interactive mode"""
    print("\n" + "="*50)
    print("NORTH AI Assistant")
    print("="*50)
    
    if north.agents:
        print("I can help you with:")
        if 'document' in north.agents:
            print("- Company and contractor information")
            print("- Project details and contacts")
            print("- Phone numbers and emails")
    else:
        print("Warning: No agents are currently available.")
        print("Please check the logs for initialization errors.")
        
    print("\nCommands:")
    print("- 'sync' - Sync Obsidian vault (updates only)")
    print("- 'reingest' - Delete all data and re-ingest from scratch")
    print("- 'status' - Show system status")
    print("- 'clear' or 'clear context' - Clear conversation context")
    print("- 'quit' or 'exit' - Exit NORTH")
    print("="*50 + "\n")
    
    consecutive_eof_errors = 0
    max_eof_errors = 3
    
    while True:
        try:
            query = input("You: ").strip()
            consecutive_eof_errors = 0  # Reset on successful input
            
            if not query:
                continue
                
            if query.lower() in ['quit', 'exit', 'q']:
                print("Goodbye!")
                break
                
            if query.lower() == 'status':
                show_status(north)
                continue
                
            if query.lower() == 'sync':
                sync_vault()
                continue
            
            if query.lower() == 'reingest':
                reingest_all()
                continue
            
            if query.lower() in ['clear', 'clear context']:
                north.context_manager.clear()
                print("Context cleared. Starting fresh conversation.")
                continue
            
            print("\nNORTH: ", end="", flush=True)
            response = north.process_query(query)
            print(response)
            print()
            
        except KeyboardInterrupt:
            print("\nGoodbye!")
            break
        except EOFError:
            consecutive_eof_errors += 1
            if consecutive_eof_errors >= max_eof_errors:
                logger.info("Multiple EOF errors detected, exiting gracefully")
                print("\nExiting due to input stream closure.")
                break
            continue
        except Exception as e:
            logger.error(f"Error in interactive mode: {e}", exc_info=True)
            print(f"\nError: {e}")
            print("Please try again.\n")


def show_status(north):
    """Show system status"""
    print("\nSystem Status:")
    print(f"- Available agents: {', '.join(north.agents.keys()) if north.agents else 'None'}")
    print(f"- Weaviate URL: {os.getenv('WEAVIATE_URL', 'Not configured')}")
    print(f"- Obsidian vault: {os.getenv('OBSIDIAN_VAULT_PATH', 'Not configured')}")
    
    # Test Weaviate connection
    if north._test_weaviate_connection():
        print("- Weaviate status: Connected")
    else:
        print("- Weaviate status: Not connected")
    print()


def sync_vault():
    """Sync Obsidian vault with proper error handling"""
    print("Syncing Obsidian vault...")
    vault_path = os.getenv('OBSIDIAN_VAULT_PATH')
    
    if not vault_path:
        print("No vault path configured in .env")
        return
        
    if not os.path.exists(vault_path):
        print(f"Vault path does not exist: {vault_path}")
        return
        
    try:
        from src.agents.obsidian.sync_obsidian import sync_vault
        sync_vault(vault_path)
    except ImportError:
        logger.error("Cannot import sync_obsidian module")
        print("Sync module not available. Please check if sync_obsidian.py exists.")
    except Exception as e:
        logger.error(f"Sync failed: {e}", exc_info=True)
        print(f"Sync failed: {e}")


def reingest_all():
    """Delete all data and re-ingest from scratch"""
    print("\nWARNING: This will DELETE all existing data and re-ingest from scratch.")
    confirm = input("Are you sure? Type 'yes' to confirm: ").strip().lower()
    
    if confirm != 'yes':
        print("Cancelled.")
        return
    
    try:
        from src.agents.obsidian.clear_and_reingest import clear_and_reingest
        clear_and_reingest()
    except ImportError:
        logger.error("Cannot import clear_and_reingest module")
        print("Reingest module not available. Please check if clear_and_reingest.py exists.")
    except Exception as e:
        logger.error(f"Reingest failed: {e}", exc_info=True)
        print(f"Reingest failed: {e}")


def main():
    """Main entry point"""
    
    # Load environment variables first
    load_dotenv()
    
    # Check command line arguments
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()
        
        if command == 'sync':
            sync_vault()
            return 0
            
        elif command == '--help' or command == '-h':
            print("NORTH AI System")
            print("\nUsage:")
            print("  python main.py          - Run interactive mode")
            print("  python main.py sync     - Sync vault changes")
            print("  python main.py --help   - Show this help")
            return 0
    
    # Default: run interactive mode
    try:
        north = NORTH()
        interactive_mode(north)
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        print("\nGoodbye!")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        print(f"\nFatal error: {e}")
        print("Please check the logs for details.")
        return 1
    finally:
        try:
            if 'north' in locals():
                north.cleanup()
        except Exception as e:
            logger.warning(f"Cleanup encountered an error: {e}", exc_info=True)
            
    return 0


if __name__ == "__main__":
    sys.exit(main())
