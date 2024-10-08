from operator import itemgetter
from typing import List, Optional
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import ConfigurableField, RunnablePassthrough, RunnableSerializable, RunnableConfig, RunnableMap
from langchain.schema import format_document, Document
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_core.output_parsers import StrOutputParser
import streamlit as st
import os

template_single_line = PromptTemplate.from_template(
    """Answer the question in a single line based on the following context.
        If there is not relevant information in the context, just say that you do not know:
        {context}


        Question: {question}
    """
)


template_detailed = PromptTemplate.from_template(
    """Answer the question in a detailed way with an idea per bullet point based on the following context.
        If there is not relevant infromation in the context, just say you do not know:
        {context}

        Question: {question}
    """
)


prompt_alternatives = {
    "detailed": template_detailed,
}

prompt = template_single_line.configurable_alternatives(
    ConfigurableField(id="output_type"),
    default_key="single_line",
    **prompt_alternatives,
)

model = ChatOpenAI(
    temperature=0,
    model_name="gpt-3.5-turbo",
)
embedding = OpenAIEmbeddings()

politic_vector_store_path = "polictic_vector_store_path.faiss"
environmental_vector_store_path = "environmental_vector_store_path.faiss"


class ConfigurableFaissRetriever(RunnableSerializable[str, List[Document]]):
    vector_store_topic: str

    def invoke(
        self, input: str, config: Optional[RunnableConfig] = None
    ) -> List[Document]:
        """Invoke the retriever."""

        vector_store_path = (
            politic_vector_store_path
            if "Politic" in self.vector_store_topic
            else environmental_vector_store_path
        )
        faiss_vector_store = FAISS.load_local(
            vector_store_path,
            embedding,
            allow_dangerous_deserialization=True,
        )
        retriever = faiss_vector_store.as_retriever(
            search_type="similarity", search_kwargs={"k": 4}
        )
        return retriever.invoke(input, config=config)


configurable_faiss_vector_store = ConfigurableFaissRetriever(
    vector_store_topic="default"
).configurable_fields(
    vector_store_topic=ConfigurableField(
        id="vector_store_topic",
        name="Vector store topic",
        description="The topic of the faiss vector store.",
    )
)

with st.expander("Upload Files to Vector Stores"):
    politic_index_uploaded_file = st.file_uploader(
        "Upload a text file to Politic vector store:", type="txt", key="politic_index"
    )
    if politic_index_uploaded_file is not None:
        string_data = politic_index_uploaded_file.getvalue().decode("utf-8")
        splitted_data = string_data.split("\n\n")
        politic_vectorstore = FAISS.from_texts(
            splitted_data, embedding=embedding)
        politic_vectorstore.save_local(politic_vector_store_path)
        st.success("Politic vector store loaded successfully!")

    environnetal_index_uploaded_file = st.file_uploader(
        "Upload a text file to the Environnemental vector store:",
        type="txt",
        key="environnetal_index",
    )
    if environnetal_index_uploaded_file is not None:
        string_data = environnetal_index_uploaded_file.getvalue().decode("utf-8")
        splitted_data = string_data.split("\n\n")
        environnetal_vectorstore = FAISS.from_texts(
            splitted_data, embedding=embedding)
        environnetal_vectorstore.save_local(environmental_vector_store_path)
        st.success("Environnemental vector store loaded successfully!")

DEFAULT_DOCUMENT_PROMPT = PromptTemplate.from_template(
    template="{page_content}")


def combine_documents(
    docs, document_prompt=DEFAULT_DOCUMENT_PROMPT, document_separator="\n\n"
):
    """Combine documents into a single string."""
    doc_strings = [format_document(doc, document_prompt) for doc in docs]
    return document_separator.join(doc_strings)


CONDENSE_QUESTION_PROMPT = PromptTemplate.from_template(
    """Given the following conversation and a follow up question, rephrase the
follow up question to be a standalone question, in its original language.

Chat History:
{chat_history}
Follow Up Input: {question}
Standalone question:"""
)


def format_chat_history(chat_history: dict) -> str:
    """Format chat history into a string."""
    buffer = ""
    for dialogue_turn in chat_history:
        actor = "Human" if dialogue_turn["role"] == "user" else "Assistant"
        buffer += f"{actor}: {dialogue_turn['content']}\n"
    return buffer


vector_store_topic = None
output_type = None

inputs = RunnableMap(
    standalone_question=RunnablePassthrough.assign(
        chat_history=lambda x: format_chat_history(x["chat_history"])
    )
    | CONDENSE_QUESTION_PROMPT
    | model
    | StrOutputParser(),
)

context = {
    "context": itemgetter("standalone_question")
    | configurable_faiss_vector_store
    | combine_documents,
    "question": itemgetter("standalone_question"),
}
chain = inputs | context | prompt | model | StrOutputParser()

st.header("Chat with your vector stores")
if os.path.exists(politic_vector_store_path) or os.path.exists(
    environmental_vector_store_path
):
    vector_store_topic = st.selectbox(
        "Choose the vector store configuration:",
        ["Politic", "Environnemental"],
    )
    output_type = st.selectbox(
        "Select the type of response:", ["detailed", "single_line"]
    )

    if "message" not in st.session_state:
        st.session_state["message"] = [
            {"role": "assistant", "content": "Hello 👋, How can I assist you ?"}
        ]

    chat_history = []

    for message in st.session_state.message:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if query := st.chat_input("Ask me anything"):
        st.session_state.message.append({"role": "user", "content": query})
        with st.chat_message("user"):
            st.markdown(query)

        response = chain.with_config(
            configurable={
                "vector_store_topic": vector_store_topic,
                "output_type": output_type,
            }
        ).invoke({"question": query, "chat_history": st.session_state.message})

        st.session_state.message.append(
            {"role": "assistant", "content": response})
        with st.chat_message("assistant"):
            st.markdown(response)
