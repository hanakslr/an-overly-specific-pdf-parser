from langchain.output_parsers import PydanticOutputParser
from langchain.prompts import PromptTemplate
from langchain_openai import ChatOpenAI

from post_processing.williston_extraction_schema import Strategies, StrategyItem


def extract_strategies(text: str) -> list[StrategyItem]:
    """
    The strategy table is sometimes a table and sometimes a colletion of headings
    and sometimes paragraphs, and we can't really rely on its format to parse it.

    Just pass the content to an LLM and it will take care of it.
    """
    my_llm = ChatOpenAI(model="gpt-4o", temperature=0)
    output_parser = PydanticOutputParser(pydantic_object=Strategies)

    prompt_template = """
You are an expert data parser. You have been given the string content of a table and I
would like you to turn it into structured JSON. 

Table text:
{text}

Based on the text content, please provide the data in the following format:
{format_instructions}
"""

    prompt = PromptTemplate(
        template=prompt_template,
        input_variables=["text"],
        partial_variables={
            "format_instructions": output_parser.get_format_instructions()
        },
    )

    chain = prompt | my_llm | output_parser

    result: Strategies = chain.invoke(
        {
            "text": text,
        }
    )

    return result.strategies
