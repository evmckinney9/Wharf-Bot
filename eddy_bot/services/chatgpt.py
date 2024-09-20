import json
import re

import openai

# from openai import OpenAI

# client = OpenAI(
#   organization='org-UUdF8oWozAPMP6dZUFO69gWo',
#   project='proj_YUM41XaGV98ej14bFT97grpS',
# )

# # # using new beta assistant API
# # async foo(bot, message_list) -> str:
# #     client = openai.OpenAI()
# #     assistant = client.beta.assistants.

async def get_chatgpt_reddit_message(bot, message_list) -> str:
    bot.logger.info("Generating chat response...")
    openai.api_key = bot.config["openai_api_key"]
    # Call assistant_response with the model_version set to "gpt-3.5-turbo"
    return await assistant_response(bot, "gpt-3.5-turbo", message_list, prompt_type="reddit")

async def get_chatgpt_response(bot, message_list) -> str:
    """Determine the best model (GPT-3.5-turbo, GPT-4, or DALLE) to handle a
    given message and generate a response.

    Args:
        bot: An instance of the bot.
        message_list: List of messages to be processed.
    Returns:
        str: The generated response from the selected model.
    """

    bot.logger.info("Generating chat response...")

    # Set the OpenAI API Key
    openai.api_key = bot.config["openai_api_key"]

    # Message to instruct the assistant to decide the appropriate model
    decision_message = {
        "role": "system",
        "content": (
            "Determine the best model to handle the following message. "
            "Err on the side of GPT-3.5-turbo whenever possible, opt for GPT-4 only if the complexity truly requires it, "
            "and choose DALLE if the message specifically asks for an image or visualization."
        ),
    }

    # Define function to be called by the assistant for generating a response
    functions = [
        {
            "name": "assistant_response",
            "description": "Get a response (textual or image) based on the selected model",
            "parameters": {
                "type": "object",
                "properties": {
                    "model_version": {
                        "type": "string",
                        "enum": ["gpt-3.5-turbo", "gpt-4", "dalle"],
                        "description": "Version of the model to use for the response or specify 'dalle' for image generation",
                    }
                },
                "required": ["model_version"],
            },
        }
    ]

    try:
        # Request the assistant's decision on the best model
        response = await openai.ChatCompletion.acreate(
            model="gpt-3.5-turbo",
            messages=[
                decision_message,
                {"role": "user", "content": message_list[-1]["content"]},
            ],
            functions=functions,
            function_call={"name": "assistant_response"},
        )
        response_message = response["choices"][0]["message"]

        # Check if the assistant decided to call the function
        if response_message.get("function_call"):
            function_name = response_message["function_call"]["name"]
            assert function_name == "assistant_response"

            function_args = json.loads(response_message["function_call"]["arguments"])

            # Log the model version selected by the assistant
            bot.logger.info(f"Chosen model/version: {function_args['model_version']}")

            function_result = await assistant_response(
                bot=bot,
                model_version=function_args["model_version"],
                messages=message_list,
            )

        return function_result

    except Exception as e:
        bot.logger.error(f"Failed to generate chat response\n{repr(e)}")
        return "Apologies, an error occurred."


async def assistant_response(bot, model_version, messages, prompt_type="basic"):
    """Generate a response (textual or image) based on the selected model
    version.

    Args:
        bot: An instance of the bot.
        model_version (str): The version of the model to use (gpt-3.5-turbo, gpt-4, or dalle).
        messages (list): List of messages to be processed.

    Returns:
        str: The generated response or image URL.
    """

    if model_version in ["gpt-3.5-turbo", "gpt-4"]:
        # Insert the basic prompt to the message list
        if prompt_type == "basic":
            basic_prompt = bot.get_basic_prompt()
        else:
            basic_prompt = bot.get_reddit_prompt()
            
        messages.insert(0, {"role": "system", "content": basic_prompt})

        response = await openai.ChatCompletion.acreate(
            model=model_version,
            messages=messages,
            max_tokens=256,
            n=1,
            temperature=0.8,
        )
        return response.choices[0].message.content

    elif model_version == "dalle":
        # Update the system prompt for DALLE interaction
        dalle_prompt = bot.get_dalle_prompt()
        messages.insert(
            0,
            {
                "role": "system",
                "content": dalle_prompt,
            },
        )  # Update the first message (system prompt)

        flavorful_response = await openai.ChatCompletion.acreate(
            model="gpt-3.5-turbo", messages=messages, max_tokens=256, n=1
        )

        # Extract the message content from the bot's response
        flavorful_content = flavorful_response.choices[0].message.content

        bot.logger.debug(
            "Flavorful response: %s",
            flavorful_content,
        )

        # Step 2: Convert the flavorful response into a concise image description
        # Assuming user's query is stored in variable `user_query`
        user_query = messages[-1]["content"]
        # Remove the starting name and the Discord tag
        cleaned_query = re.sub(r"(@[A-Za-z0-9_]+: )?<@(\d+)> ", "", user_query)

        bot.logger.debug("User query: %s", cleaned_query)

        conversion_instruction = (
            f"Original request: '{cleaned_query}'. Extract key visual attributes from the user's request and the provided response. "
            "Extract ONLY the key visual attributes from the provided response.  "
            "and thematic/emotional tones. Simplify the response into a direct and vivid image description for DALLE. "
            "Focus on the main elements, ensuring clarity and conciseness."
            "Do not continue the conversation or add any new information."
            "Prompts for DALLE should be a comma separated list of explicit visual attributes."
        )
        messages_conversion = [
            {
                "role": "system",
                "content": conversion_instruction,
            },
            {
                "role": "user",
                "content": flavorful_content,
            },
        ]

        textual_response = await openai.ChatCompletion.acreate(
            model="gpt-3.5-turbo",
            messages=messages_conversion,
            max_tokens=128,
            n=1,
        )

        image_prompt = textual_response.choices[0].message.content
        image_prompt = image_prompt.replace("Description:", "").strip()

        bot.logger.info(
            "Generating image response using the following prompt: %s",
            image_prompt,
        )

        # Generate the image using DALLE
        image_response = await openai.Image.acreate(
            prompt=image_prompt, n=1, size="1024x1024"
        )

        return image_response["data"][0]["url"]
