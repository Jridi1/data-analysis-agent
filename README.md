# CSV Data Analyst Agent: model written code that runs in a sandbox

An analysis agent for CSV files. You ask a question in plain English, an LLM writes Python code, and the code runs inside a locked down Docker container instead of in the agent's own process. The output (numbers, tables, charts) comes back to the model, which explains it. If the code fails, the error goes back to the model so it can fix its own script.

The project started with the standard LangChain pandas agent, which runs model written code inside the application. That version leaked the user's API key and a GitHub token when asked to print the environment. This repository replaces it with a sandboxed runner and a test suite that attacks it.

## How it works

1. The user types a question in the terminal.
2. The model (Groq, `openai/gpt-oss-120b`) calls one tool, `run_python`, with a complete Python script.
3. The runner starts a fresh container, sends the script through standard input, and collects the output with a size cap and a timeout.
4. The container is destroyed after every call. Anything that looks like an API key is redacted from the output, and every run is appended to an audit log.
5. The output goes back to the model, which fixes errors or writes the final answer.

The API key lives only in the agent process. The container receives code and nothing else.

## Safety layers

| Risk | Control | How it is checked |
|---|---|---|
| Model code reads secrets | Container starts with an empty environment, and the project folder (with `.env`) is never mounted | Test with a canary secret in the host environment, and an environment dump run through the agent |
| Code reads or deletes host files | Read only root filesystem, only one data file mounted read only, one writable output folder | Tests for host paths, writing to the data folder, and the test file mount |
| Data exfiltration | No network inside the container | Test that an outbound request fails |
| Infinite loop | Timeout, and the container itself is killed | Test with a busy loop |
| Memory bomb, fork bomb | Memory, CPU and process count limits | Tests with a large allocation and a process flood |
| Print flood | Output is read in chunks and capped | Test with an endless print loop |
| Key printed by mistake | Pattern based redaction of key shapes in all output and logs | Test that a fake key is redacted |
| Test data used by accident | The test file is mounted read only and the prompt forbids using it before the final evaluation | Test that the file cannot be opened for writing |

Two results through the agent: asked to print the environment, it showed no key and an empty home folder. Asked to save a file to the data folder, the write failed with a read only error and the agent saved to the output folder instead. Some risky requests were refused or avoided by the model on its own. That is useful, but it is not counted as containment, because it depends on the model's choice.

## Quick start

1. Install Docker and Python 3.12 or newer.
2. Clone the repository and create a virtual environment.

```bash
git clone https://github.com/Jridi1/data-analysis-agent.git
cd data-analysis-agent
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

3. Add your Groq key. Copy the example file and edit it.

```bash
cp .env.example .env
```

4. Put the two dataset files in a `data` folder: `transactions_train.csv` and `transactions_test.csv` (the Digital Payment Fraud Detection Benchmark with 400,000 transactions and temporal drift). https://www.kaggle.com/datasets/rohit8527kmr7518/digital-payment-fraud-detection-benchmark
5. Build the sandbox image and start the agent.

```bash
docker build -t csv-sandbox sandbox_image/
python sandbox_agent.py
```

## Tests

The tests send hostile code straight to the runner, with no model involved, so they are free, fast and repeatable:

```bash
pytest test_sandbox.py -v
```

## Example analysis: fraud detection under drift

The agent was used to run a full analysis of a synthetic payments dataset, in 11 phases with strict time based validation. The sealed test file (October to December) was scored once, by a model chosen on earlier months. The full report is in `docs/report.md`.

* Fraud rate steps from 1.40% in June to 1.98% in July. After June, fraud moves toward smaller amounts, international transactions and denser velocity.
* One column, `post_auth_risk_score`, separates fraud from legit perfectly (ROC AUC 1.0). It leaks the target and was excluded from every model.
* Final model: logistic regression with 15 numeric features. Test PR-AUC 0.369885 and ROC AUC 0.843889. Flagging the top 2% of scores catches 819 of the 1,983 frauds at precision 0.410115.
* Blind spot: fraud with 3 or fewer transactions in 24 hours is never flagged, and may be mostly label noise.

Every number in the report was copied from sandbox output and checked by an independent rerun. The process also showed the weak points of the agent: a model that fills gaps with invented text when it cannot see the data, and silent truncation of long outputs. Both were handled with explicit rules and checks.

## Limitations

* A standard Docker container shares the host kernel. It is strong, but not as strong as gVisor or a throwaway virtual machine, which would be the next step.
* Each call starts a fresh process, so the model must reload the data every time. There is no memory between questions.
* Whatever the code prints is sent back to the LLM provider, so do not print private data.
* The model sometimes produces malformed tool calls, and the free tier has token limits per minute. The agent retries malformed calls and stops on requests that are too large.
* The example dataset is synthetic.

## Project structure

* `sandbox_agent.py`: the agent loop and the system prompt
* `sandbox_runner.py`: the container runner with all limits, redaction and logging
* `sandbox_image/Dockerfile`: the image with pandas, scikit-learn and matplotlib
* `test_sandbox.py`: attack tests for the runner
* `agents.py`: the original pandas agent that runs code in process, kept only for comparison. Do not expose it to untrusted users.
* `docs/report.md`: the analysis report
* `.env.example`: template for the API key

## Author

Abderrahim Jridi