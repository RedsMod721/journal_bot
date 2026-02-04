import time
import logging
from httpx import ConnectError

# Assuming Logger is already set up
logger = logging.getLogger("OllamaLogger")

class Ollama:
    @staticmethod
    def list_models():
        retry_attempts = 3
        for attempt in range(retry_attempts):
            try:
                # Attempt to get the models from Ollama server
                return ollama.list()["models"]
            except ConnectError as e:
                logger.warning(f"Connection refused, attempt {attempt + 1} of {retry_attempts}: {e}")
                if attempt < retry_attempts - 1:
                    time.sleep(2)  # Wait for 2 seconds before retrying
                else:
                    logger.error("Failed to connect after multiple attempts.")
                    return []  # Return empty list after retrying
            except Exception as e:
                logger.error(f"Failed to list models: {e}")
                return []  # Return empty list on other exceptions

#from langchain_community.chat_models import ChatOllama
from langchain_ollama import ChatOllama 
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

# Local Llama3 
llm = ChatOllama(
    model="llama3",
    keep_alive=-1, # keep the model loaded indefinitely
    temperature=0,
    max_new_tokens=512)

prompt = ChatPromptTemplate.from_template("Write me a 500 word article on {topic} from the perspective of a {profession}. ")

# using LangChain Expressive Language chain syntax
chain = prompt | llm | StrOutputParser()

# print(chain.invoke({"topic": "LLMs", "profession": "shipping magnate"}))

for chunk in chain.stream({"topic": "LLMs", "profession": "shipping magnate"}):
    print(chunk, end="", flush=True)