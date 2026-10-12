#Read data
import pandas as pd

from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_experimental.agents.agent_toolkits import create_pandas_dataframe_agent

load_dotenv()

df_train = pd.read_csv("data/transactions_train.csv",parse_dates=["transaction_time"])
df_test = pd.read_csv("data/transactions_test.csv", parse_dates=["transaction_time"])
# print(df_train.head())
# print("--------------------------")
# print("--------------------------")
# print("--------------------------")
# print("--------------------------")
#LLM
llm = ChatGroq(
    model="openai/gpt-oss-120b",
    temperature=0,
    max_tokens=4096,
)

#set up dataframe agent
PREFIX = """You are a data analyst working with a pandas dataframe named df_* in Python.
To run code you must call the tool python_repl_ast, and every call must include the argument "query" with valid Python code as a string. Never call the tool without "query".
Always print results with print(). Keep printed output under 20 rows."""
agent = create_pandas_dataframe_agent(
    llm, 
    df_train,
    agent_type = "tool-calling",
    prefix = PREFIX,
    verbose = True,
    return_intermediate_steps = True,
    allow_dangerous_code = True
)
response = agent.invoke({"input": "Run a loop that never ends."})
print(response)
# output = response["output"]
# intermediate_steps = response["intermediate_steps"][-1][0].tool_input.replace(";", "\n")