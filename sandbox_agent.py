import groq
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langchain_groq import ChatGroq
from pydantic import BaseModel, Field

from sandbox_runner import run_in_sandbox

load_dotenv()

SYSTEM_PROMPT = """You are a data analyst for a fraud detection dataset.

Your only tool is run_python. It runs a complete Python script in an isolated sandbox.
Sandbox rules:
1. Every call starts a fresh Python process. Variables, imports and loaded data are NOT kept between calls, so every script must import its libraries and reload the data.
2. The training data is the CSV file /data/transactions_train.csv (read only). Load it with:
   pd.read_csv("/data/transactions_train.csv", parse_dates=["transaction_time"])
3. Write any file you want to keep (charts, tables) to /output. Save charts as PNG with matplotlib.
4. There is no internet. Available libraries: pandas, numpy, scipy, scikit-learn, matplotlib.
5. Results only count if you print() them. Print at most 20 rows and keep the output short.
6. A script that runs longer than 60 seconds is killed. If you get an error, read it, fix the code and try again.

Dataset columns: transaction_id, transaction_time, customer_id, merchant_id, account_age_days, credit_score_band, kyc_level, avg_monthly_spend, merchant_risk_score, transaction_amount, payment_channel, device_type, is_international, ip_risk_score, txn_count_1h, txn_count_24h, failed_txn_count_24h, geo_distance_from_last_txn, amount_deviation_from_user_mean, is_fraud (target, 1 is fraud), post_auth_risk_score.

Analysis rules:
1. Never use post_auth_risk_score as a model feature. It leaks the target.
2. Split by time only, never randomly. Use exactly the training and validation months named in the question.
3. Primary metric is PR-AUC (average precision), then ROC AUC.
4. Use random_state=42.
5. Always run code to get numbers. Never calculate or guess in your head.
6. If the question is not about this dataset, say you only help with this dataset.
7. Keep the final answer short and state the numbers you computed.
8. In the final answer, copy every number exactly as printed in the sandbox output. Never recompute, re-round or reformat a number.
9. Never use transaction_id, customer_id, merchant_id, transaction_time or any month, day or time column derived from it as a model feature. Never use post_auth_risk_score.
10. Keep every script short and simple: no comments, no unused imports, no extra prints.When you print a table, use to_string() so that no column or row is hidden.
11. The sealed test file is /data/transactions_test.csv. Use it only when the question explicitly asks for the final test evaluation. Never use it for exploration, training, tuning or choosing thresholds.
"""



class CodeInput(BaseModel):
    code: str = Field(
        description="A complete Python script. It starts from a fresh interpreter, so it must "
        "import its libraries and reload the data. Use print() to show results."
    )


@tool(args_schema=CodeInput)
def run_python(code: str) -> str:
    """
    Run a Python script in an isolated sandbox and return what it printed.
    Use this tool for every calculation, table, chart or model.

    Args:
        code (str): A complete Python script that prints its results.

    Returns:
        (str): The printed output, or the error message if the script failed.
    """
    result = run_in_sandbox(code)

    parts = []
    if result["stdout"]:
        parts.append("STDOUT:\n" + result["stdout"][:4000])
    if result["stderr"]:
        parts.append("STDERR:\n" + result["stderr"][-1200:])  # the end of a traceback matters most
    if result["error"]:
        parts.append("SANDBOX ERROR: " + result["error"])
    if not parts:
        parts.append("The script ran but printed nothing. Use print() to see results.")
    return "\n\n".join(parts)


llm = ChatGroq(model="openai/gpt-oss-120b", temperature=0, max_tokens=3000)
llm_with_tools = llm.bind_tools([run_python])


def ask_llm(messages, tries=3):
    for attempt in range(1, tries + 1):
        try:
            return llm_with_tools.invoke(messages)
        except groq.APIError as e:
            code = getattr(e, "status_code", None)
            if code == 413:
                raise RuntimeError("Request too large for the token limit. Ask a smaller question or lower max_tokens.")
            if code == 429:
                print("Rate limit reached, waiting 30 seconds")
                time.sleep(30)
                continue
            print(f"API error, retry {attempt}/{tries}: {str(e)[:150]}")
            messages = messages + [HumanMessage(content=(
                "Your last tool call was cut off or malformed. "
                "Call run_python again with a shorter, simpler script."
            ))]
    raise RuntimeError("The model kept producing invalid calls.")


def run_agent(question: str, max_steps: int = 8) -> dict:
    messages = [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=question)]
    runs = []

    for _ in range(max_steps):
        ai_message = ask_llm(messages)
        messages.append(ai_message)

        if not ai_message.tool_calls:
            return {"answer": ai_message.content, "runs": runs}

        for call in ai_message.tool_calls:
            if call["name"] != "run_python":
                output = f"Unknown tool {call['name']}. Only run_python exists."
            else:
                code = call["args"].get("code", "")
                print("\n--- code sent to the sandbox ---")
                print(code)
                try:
                    output = run_python.invoke(call["args"])
                except Exception as e:  # for example a missing "code" argument
                    output = f"Tool call failed: {e}"
                print("--- sandbox output ---")
                print(output)
                runs.append({"code": code, "output": output})

            messages.append(ToolMessage(content=output, tool_call_id=call["id"]))

    return {"answer": "Stopped: too many steps.", "runs": runs}


if __name__ == "__main__":
    while True:
        question = input("\nQuestion (or 'exit'): ").strip()
        if question.lower() in {"exit", "quit", ""}:
            break
        result = run_agent(question)
        print("\n=== ANSWER ===")
        print(result["answer"])