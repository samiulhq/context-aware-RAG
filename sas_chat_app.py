import os
import gradio as gr
from openai import AzureOpenAI
from pinecone import Pinecone

# Load environment variables from .env file
def load_env():
    if os.path.exists('.env'):
        with open('.env', 'r') as f:
            for line in f:
                if line.strip() and not line.startswith('#'):
                    key, value = line.strip().split('=', 1)
                    os.environ[key] = value

load_env()

# Initialize clients
client = AzureOpenAI(
    api_key=os.environ["AZURE_OPENAI_API_KEY"],
    api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-02-15-preview"),
    azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"]
)

pc = Pinecone(api_key=os.environ["PINECONE_API_KEY"])
index = pc.Index('sas-code-chunks')

embedding_model = os.environ.get("AZURE_OPENAI_EMBEDDING_MODEL", "text-embedding-ada-002")
chat_model = os.environ["AZURE_OPENAI_DEPLOYMENT"]


def retrieve_relevant_chunks(query: str, top_k: int = 3):
    """Retrieve relevant SAS code chunks from Pinecone"""
    response = client.embeddings.create(
        model=embedding_model,
        input=query
    )
    query_embedding = response.data[0].embedding
    
    results = index.query(
        vector=query_embedding,
        top_k=top_k,
        include_metadata=True
    )
    
    relevant_chunks = []
    for i, match in enumerate(results['matches']):
        filepath = match['metadata'].get('filepath', '')
        
        full_file_content = ""
        if filepath and os.path.exists(filepath):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    full_file_content = f.read()
            except Exception as e:
                full_file_content = "File not accessible"
        
        relevant_chunks.append({
            'rank': i + 1,
            'score': match['score'],
            'chunk_type': match['metadata']['chunk_type'],
            'name': match['metadata']['name'],
            'code': match['metadata']['code'],
            'explanation': match['metadata']['explanation'],
            'filename': match['metadata'].get('filename', ''),
            'line_start': match['metadata'].get('line_start', 0),
            'line_end': match['metadata'].get('line_end', 0),
            'full_file_content': full_file_content
        })
    
    return relevant_chunks


def build_context(chunks):
    """Build context from retrieved chunks"""
    context = ""
    for chunk in chunks:
        context += f"\n{'='*70}\n"
        context += f"CHUNK {chunk['rank']}: {chunk['chunk_type']} - {chunk['name']}\n"
        context += f"File: {chunk['filename']} (Lines {chunk['line_start']}-{chunk['line_end']})\n"
        context += f"{'='*70}\n"
        
        if chunk['full_file_content']:
            context += f"\n--- FULL FILE CONTEXT ---\n{chunk['full_file_content']}\n"
        
        context += f"\n--- SPECIFIC CHUNK ---\n"
        context += f"Explanation: {chunk['explanation']}\n"
        context += f"Code:\n{chunk['code']}\n"
    
    return context


def chat_with_sas_assistant(message, history):
    """Main chat function"""
    chunks = retrieve_relevant_chunks(message, top_k=3)
    context = build_context(chunks)
    
    prompt = f"""You are a SAS programming expert assistant. Answer the user's question based on the following relevant SAS code chunks.

RETRIEVED CONTEXT:
{context}

USER QUESTION: {message}

Provide a clear, helpful answer based on the context above. Reference specific code examples when relevant."""
    
    response = client.chat.completions.create(
        model=chat_model,
        messages=[
            {"role": "system", "content": "You are a helpful SAS programming assistant."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.3,
        max_tokens=1500
    )
    
    answer = response.choices[0].message.content
    
    chunks_info = "\n\n---\n**📚 Retrieved Chunks:**\n"
    for chunk in chunks:
        chunks_info += f"- {chunk['chunk_type']}: `{chunk['name']}` (score: {chunk['score']:.3f})\n"
        chunks_info += f"  📁 {chunk['filename']} (Lines {chunk['line_start']}-{chunk['line_end']})\n"
    
    return answer + chunks_info


# SAS branding HTML/CSS - matching official SAS interface
sas_header = """
<style>
    /* Hide footer */
    footer {display: none !important;}
    .footer {display: none !important;}
    
    /* Official SAS Colors */
    :root {
        --sas-blue: #0074BD;
        --sas-blue-hover: #005A94;
        --sas-white: #FFFFFF;
        --sas-light-gray: #F7F7F7;
    }
    
    /* Main container styling */
    .gradio-container {
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif !important;
        background-color: var(--sas-light-gray) !important;
    }
    
    /* Button styling - SAS Blue */
    button.primary, button[type="submit"], .submit-btn {
        background-color: var(--sas-blue) !important;
        border-color: var(--sas-blue) !important;
        color: white !important;
        font-weight: 500 !important;
    }
    
    button.primary:hover, button[type="submit"]:hover, .submit-btn:hover {
        background-color: var(--sas-blue-hover) !important;
        border-color: var(--sas-blue-hover) !important;
    }
    
    /* Chat container */
    .chatbot {
        background-color: white !important;
        border: 1px solid #E5E5E5 !important;
    }
    
    /* Example buttons */
    .examples button {
        border: 1px solid var(--sas-blue) !important;
        color: var(--sas-blue) !important;
        background-color: white !important;
    }
    
    .examples button:hover {
        background-color: #F0F8FF !important;
    }
</style>

<div style="background-color: #0074BD; color: white; padding: 16px 24px; margin: -20px -20px 20px -20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
    <h1 style="color: white !important; margin: 0; font-size: 1.8em; font-weight: 400; letter-spacing: 0.5px;">SAS® Clinical Programming Assistant</h1>
    <p style="margin: 8px 0 0 0; font-size: 0.95em; opacity: 0.95;"> Code assitance based on your custom code repository</p>
</div>
"""

# Create Gradio interface with HTML header for styling
with gr.Blocks() as demo:
    gr.HTML(sas_header)
    
    gr.ChatInterface(
        fn=chat_with_sas_assistant,
        examples=[
            "How do I calculate SDTM DY variable ?",
        "How do I derive EPOCH variable using SE SDTM dataset?",
        "How to merge datasets in SAS?",
        "How can I create Adverse Events by SOC and Preferred Term?"
        ],
        chatbot=gr.Chatbot(height=450),
    )


if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860)