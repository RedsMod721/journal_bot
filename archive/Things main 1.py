# Models
import ollama
from langchain_ollama import ChatOllama 
from langchain_core.prompts import PromptTemplate
from pydantic import BaseModel, Field, field_validator
from langchain_experimental.llms.ollama_functions import OllamaFunctions


# Pydantic Schema for structured response
class Message_type(BaseModel):
    type: str = Field(description="The message type: 1.'information log' or 2.'question' or 3.'task'", required=True)

    # Validator to ensure the 'type' is one of the predefined options
    @field_validator('type')
    def check_type_validity(cls, v):
        valid_types = ['information log', 'question', 'task', 'mixed input']
        if v not in valid_types:
            raise ValueError(f"Invalid type '{v}'. Must be one of {valid_types}.")
        return v
    
    def model_construct(self):
        # This method should return the schema as expected by Ollama
        return {
            "type": self.type
        }

context = """ANSWER OPTIONS:
Answer1: "**'information log'**" description: Any input that provides facts, updates, or descriptive content intended solely for recording, acknowledgment, or contextual reference. These inputs do not contain a direct or implied request for action, clarification, or further information. 

Characteristics:
- **No interrogative elements**: The input does not end with a question mark, use questioning words (e.g., "what," "why," "how"), or imply a need for a response.
- **Static content**: It serves as passive information rather than triggering a process or response.
- **Declarative tone**: Inputs are statements rather than inquiries or commands.

Examples:
- "The meeting is scheduled for tomorrow at 3 PM."
- "This software update fixes several bugs."
- "The document has 20 pages, organized into five sections."
- "Sales increased by 15% last quarter."

Answer2: "**'question'**" description: Any input intended to solicit an explicit answer, clarification, or explanation from the agent. A "question" is characterized by a direct or implied request for information or guidance, rather than introspection, reflection, or rhetorical expression.

Characteristics:
- **Explicit request**: The input seeks a response or action, either directly (e.g., "What time is it?") or indirectly (e.g., "Could you explain this?").
- **Clarification intent**: It demonstrates a need for understanding or further details.
- **Linguistic cues**: Commonly uses interrogative words (e.g., "who," "what," "when," "where," "why," "how") or ends with a question mark.

Non-questions (introspective or rhetorical statements):
- Statements expressing personal reflection or thoughts without seeking external input are not questions, even if they contain interrogative words or a questioning tone.
  - Example: "Sometimes I wonder, will it be okay if I die?" (Log, as it reflects personal introspection and does not seek an answer.)
  - Example: "I think about what could happen if we fail." (Log, expressing reflection rather than inquiry.)

Examples of true "questions":
- "What time is the meeting?"
- "How can I improve this document?"
- "Can you confirm if this data is correct?"

Answer3: "**'task'**" description: Any input that explicitly or implicitly directs an action to be taken. This can range from providing a summary to generating a creative output or solving a specific problem.
Examples:
- "Summarize the attached document in 200 words."
- "Generate a code snippet for sorting a list in Python."
- "Draft an email template for customer feedback requests."

Answer4: "**'mixed input'**" description: Any input that combines elements of multiple categories (e.g., question and task, information and question), making it challenging to classify exclusively under a single type. Use this category when the input simultaneously serves two or more purposes.

Characteristics:
- **Overlapping categories**: The input blends features of "information," "question," or "task" in a way that requires additional interpretation.
- **Dual intent**: It may simultaneously provide information while requesting an action or clarification.
- **Ambiguous framing**: The input lacks a clear primary intent or leans equally towards multiple categories.

Examples:
- "Can you confirm if this report is correct and summarize its key findings?" (Both question and task.)
- "I noticed an error in the document; could you fix it?" (Information and task.)
- "Here is the latest data. Do you think it’s accurate?" (Information and question.)

Non-Examples:
- Inputs that fit predominantly into a single category:
  - "What is the deadline for this project?" (Question only.)
  - "Summarize the attached document." (Task only.)
  - "The sales report is in the shared folder." (Information log only.)
"""

# Prompt template llama3
prompt = PromptTemplate.from_template(
    """<|begin_of_text|><|start_header_id|>system<|end_header_id|>
    You are an expert message analyst with a PhD specialised in categorising user messages. You have been defining the message's category for 20 years. The answer MUST be "'information log' OR 'question' OR 'task' OR 'mixed input'. Return your answer in JSON.
    <|eot_id|><|start_header_id|>user<|end_header_id|>
QUESTION: {question} \n
CONTEXT: {context} \n
JSON:
<|eot_id|>
<|start_header_id|>assistant<|end_header_id|>
 """
)

# Chain
llm = ChatOllama(model="llama3.2", 
                      format="json", 
                      temperature=0)

structured_llm = llm.with_structured_output(Message_type)
chain = prompt | structured_llm

# Correctly map the input variables to the prompt template
response = chain.invoke({
    "question": "sometimes I wonder if friends like me..",  # Correct key: question
    "context": context  # Correct key: context
})

# Print the response
print(response)