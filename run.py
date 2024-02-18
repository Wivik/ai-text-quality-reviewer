from flask import Flask
import markdown
from flask import render_template, request, redirect, url_for, flash, session
from flask_wtf.csrf import CSRFProtect
from transformers import AutoTokenizer
import math

import utils.db as db
import utils.functions as f
from urllib.parse import urljoin

import os
import requests
import json
from ast import literal_eval

default_system_prompt = "Tu es un relecteur de livre écrit en français qui propose des corrections de qualité : langue, syntaxe, formulation, incohérences, etc. Tu proposes des corrections dans le texte en utilisant la syntaxe markdown pour les mettre en valeur. Tu réponds en français et ne cherches pas à traduire le texte dans une autre langue."

def create_app():
    # create and configure the app
    app = Flask(__name__, instance_relative_config=True)

    app.config['SECRET_KEY'] = os.urandom(32)
    app.config['SETTINGS_DB'] = 'settings.db'

    db.create_settings_database(app.config['SETTINGS_DB'])

    csrf = CSRFProtect()
    csrf.init_app(app)

    ## load initial config
    app.config['LLM_SYSTEM_PROMPT'] = db.get_setting(app.config['SETTINGS_DB'], 'LLM_SYSTEM_PROMPT', default_system_prompt)
    app.config['LLM_API_BASE_URL'] = db.get_setting(app.config['SETTINGS_DB'], 'LLM_API_BASE_URL', 'https://api.infomaniak.com/1/llm/')
    app.config['LLM_PRODUCT_ID'] = db.get_setting(app.config['SETTINGS_DB'], 'LLM_PRODUCT_ID', None)
    app.config['LLM_ACCESS_TOKEN'] = db.get_setting(app.config['SETTINGS_DB'], 'LLM_ACCESS_TOKEN', None)
    app.config['LLM_MAX_TOKENS_PER_OUTPUT'] = db.get_setting(app.config['SETTINGS_DB'], 'LLM_MAX_TOKENS_PER_OUTPUT', '1024')
    app.config['LLM_MODEL_PROFILE'] = db.get_setting(app.config['SETTINGS_DB'], 'LLM_MODEL_PROFILE', 'standard')
    app.config['LLM_REQUEST_TIMEOUT'] = db.get_setting(app.config['SETTINGS_DB'], 'LLM_REQUEST_TIMEOUT', '60')
    app.config['LLM_COST_PER_10K_TOKEN_INPUT'] = db.get_setting(app.config['SETTINGS_DB'], 'LLM_COST_PER_10K_TOKEN_INPUT', '0.005')
    app.config['LLM_COST_PER_10K_TOKEN_OUTPUT'] = db.get_setting(app.config['SETTINGS_DB'], 'LLM_COST_PER_10K_TOKEN_OUTPUT', '0.015')
    app.config['LLM_MODEL_NAME'] = db.get_setting(app.config['SETTINGS_DB'], 'LLM_MODEL_NAME', 'mistralai/Mixtral-8x7B-Instruct-v0.1')

    return app

app = create_app()


## reload application settings
def reload_configuration():
    app.config['LLM_SYSTEM_PROMPT'] = db.get_setting(app.config['SETTINGS_DB'], 'LLM_SYSTEM_PROMPT', default_system_prompt)
    app.config['LLM_API_BASE_URL'] = db.get_setting(app.config['SETTINGS_DB'], 'LLM_API_BASE_URL', 'https://api.infomaniak.com/1/llm/')
    app.config['LLM_PRODUCT_ID'] = db.get_setting(app.config['SETTINGS_DB'], 'LLM_PRODUCT_ID', None)
    app.config['LLM_ACCESS_TOKEN'] = db.get_setting(app.config['SETTINGS_DB'], 'LLM_ACCESS_TOKEN', None)
    app.config['LLM_MAX_TOKENS_PER_OUTPUT'] = db.get_setting(app.config['SETTINGS_DB'], 'LLM_MAX_TOKENS_PER_OUTPUT', '1024')
    app.config['LLM_MODEL_PROFILE'] = db.get_setting(app.config['SETTINGS_DB'], 'LLM_MODEL_PROFILE', 'standard')
    app.config['LLM_REQUEST_TIMEOUT'] = db.get_setting(app.config['SETTINGS_DB'], 'LLM_REQUEST_TIMEOUT', '60')
    app.config['LLM_COST_PER_10K_TOKEN_INPUT'] = db.get_setting(app.config['SETTINGS_DB'], 'LLM_COST_PER_10K_TOKEN_INPUT', '0.005')
    app.config['LLM_COST_PER_10K_TOKEN_OUTPUT'] = db.get_setting(app.config['SETTINGS_DB'], 'LLM_COST_PER_10K_TOKEN_OUTPUT', '0.015')
    app.config['LLM_MODEL_NAME'] = db.get_setting(app.config['SETTINGS_DB'], 'LLM_MODEL_NAME', 'mistralai/Mixtral-8x7B-Instruct-v0.1')

## estimate token function
def estimate_token_count(text, model_name=app.config['LLM_MODEL_NAME']):
    """
    Estimate the number of tokens for a given text using a specified tokenizer model.

    Args:
    - text (str): The input text to tokenize.
    - model_name (str): The model name of the tokenizer to use for estimation.

    Returns:
    - int: Estimated token count.
    """
    # Load the tokenizer for the specified model
    tokenizer = AutoTokenizer.from_pretrained(model_name)

    # Tokenize the input text and count the tokens
    tokens = tokenizer.tokenize(text)
    token_count = len(tokens)

    return token_count

def calculate_cost(input_token_count, price_per_10k_tokens_input, price_per_10k_tokens_output, token_output):
    """
    Calculate the cost of processing a number of tokens based on a specified price per 10k tokens.

    Args:
    - token_count (int): The number of tokens.
    - price_per_10k_tokens (float): Price per 10,000 tokens.

    Returns:
    - float: The calculated cost.
    """
    # Calculate how many sets of 10k tokens, rounding up
    sets_of_10k_input = math.ceil(int(input_token_count) / 10000)
    sets_of_10k_output = math.ceil(int(token_output) / 10000)
    input_cost = sets_of_10k_input * float(price_per_10k_tokens_input)
    output_cost = sets_of_10k_output * float(price_per_10k_tokens_output)
    return input_cost, output_cost

def execute_prompt(api_base_url, product_id, api_key, model_profile, system_prompt, max_new_tokens, prompt, request_timeout):
    full_url = urljoin(api_base_url, product_id)
    payload = {
        "messages": [
            {
                "content": prompt,
                "role": "user"
            }
        ], 
        "max_new_tokens": max_new_tokens,
        "system_prompt": system_prompt,
        "profile_type": model_profile,
    }


    headers = {
        'Authorization': 'Bearer '+ api_key,
        'Content-Type': 'application/json',
    }

    req = requests.request("POST", url = full_url , json = payload, headers = headers, timeout = int(request_timeout))
    return payload, req

def markdown_filter(text):
    return markdown.markdown(text, extensions=['markdown.extensions.extra', 'markdown.extensions.tables', 'markdown.extensions.nl2br', 'pymdownx.tilde'])

app.jinja_env.filters['markdown'] = markdown_filter


## routes


@app.route('/')
def index():
    return render_template("index.html")

@app.route('/setup', methods=('GET', 'POST'))
def setup():
    if request.method == 'POST':
        ## update the settings
        db.register_setting(app.config['SETTINGS_DB'], 'LLM_SYSTEM_PROMPT', request.form['llm_system_prompt'])
        db.register_setting(app.config['SETTINGS_DB'], 'LLM_API_BASE_URL', request.form['llm_api_base_url'])
        db.register_setting(app.config['SETTINGS_DB'], 'LLM_PRODUCT_ID', request.form['llm_product_id'])
        if request.form['llm_access_token'] != '':
            db.register_setting(app.config['SETTINGS_DB'], 'LLM_ACCESS_TOKEN', request.form['llm_access_token'])
        db.register_setting(app.config['SETTINGS_DB'], 'LLM_MAX_TOKENS_PER_OUTPUT', request.form['llm_max_output_tokens'])
        db.register_setting(app.config['SETTINGS_DB'], 'LLM_MODEL_PROFILE', request.form['llm_model_profile'])
        db.register_setting(app.config['SETTINGS_DB'], 'LLM_REQUEST_TIMEOUT', request.form['llm_request_timeout'])
        db.register_setting(app.config['SETTINGS_DB'], 'LLM_COST_PER_10K_TOKEN_INPUT', request.form['llm_cost_per_10k_token_input'])
        db.register_setting(app.config['SETTINGS_DB'], 'LLM_COST_PER_10K_TOKEN_OUTPUT', request.form['llm_cost_per_10k_token_ouput'])

        ## reload configuration
        reload_configuration()

        flash('Configuration successfully updated', category='info')
        return redirect(url_for('setup'))
    else:

        return render_template("setup/setup.html")

@app.route('/review', methods=('GET', 'POST'))
def review():
    if request.method == 'POST':
        if request.form['simulation'] == '1':
            input_token_estimation = estimate_token_count(request.form['prompt'])

            input_token_cost, output_token_cost = calculate_cost(input_token_estimation, app.config['LLM_COST_PER_10K_TOKEN_INPUT'], app.config['LLM_COST_PER_10K_TOKEN_OUTPUT'], app.config['LLM_MAX_TOKENS_PER_OUTPUT'])

            result = {
                'prompt': request.form['prompt'],
                'input_token_estimation': input_token_estimation,
                'input_token_cost': input_token_cost,
                'output_token_cost': output_token_cost
            }
            return render_template("review/output.html", result=result)
        else:
            payload, result = execute_prompt(api_base_url=app.config['LLM_API_BASE_URL'], product_id=app.config['LLM_PRODUCT_ID'], api_key=app.config['LLM_ACCESS_TOKEN'], model_profile=app.config['LLM_MODEL_PROFILE'], system_prompt=app.config['LLM_SYSTEM_PROMPT'], max_new_tokens=app.config['LLM_MAX_TOKENS_PER_OUTPUT'], prompt=request.form['prompt'], request_timeout=app.config['LLM_REQUEST_TIMEOUT'])

            # payload = "{'messages': [{'content': 'test', 'role': 'user'}], 'max_new_tokens': '5000', 'system_prompt': \"Tu es un relecteur de livre écrit en français qui propose des corrections syntaxiques, grammaticales, ou reformulations. Tu ignores le caractère des guillemets ou l'apostrophe. Tu ne traduis pas le texte dans une autre langue. Tu utilises la syntaxe markdown pour pointer les corrections\", 'profile_type': 'standard'}"

            # result = "{'result': 'success', 'data': {'model': 'mixtral', 'created': 1708267276, 'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': 'Here is your text with some suggested changes:\n\n*test*\n\n- It would be better to write this word in uppercase as it is often used as an abbreviation for test in English. However, if you intended to use it as a verb meaning to try something out, then leaving it in lowercase is appropriate. In that case, the correct spelling would be tester.'}, 'finish_reason': 'eos_token'}], 'usage': {'input_tokens': 146, 'output_tokens': 87, 'total_tokens': 233}}}"

            print('paylord et result')
            print(payload)
            print(result)
            # print(result.status_code)
            # print(result.text)
            # print(result.json())

            db.insert_prompt(app.config['SETTINGS_DB'], str(payload), str(result.json()))

            latest_prompt = db.get_latest_prompt(app.config['SETTINGS_DB'])
            prompt_request = latest_prompt[1]
            prompt_output = latest_prompt[2]

            cleaned_prompt_request = literal_eval(prompt_request)
            cleaned_prompt_output = literal_eval(prompt_output)

            input_tokens = cleaned_prompt_output['data']['usage']['input_tokens']
            output_tokens = cleaned_prompt_output['data']['usage']['output_tokens']
            print(input_tokens)
            print(output_tokens)

            input_token_cost, output_token_cost = calculate_cost(input_token_count=input_tokens, price_per_10k_tokens_input=app.config['LLM_COST_PER_10K_TOKEN_INPUT'], price_per_10k_tokens_output=app.config['LLM_COST_PER_10K_TOKEN_OUTPUT'], token_output=output_tokens)

            full_result = {
                'prompt': cleaned_prompt_request['messages'][0]['content'],
                'request': cleaned_prompt_request,
                'output': cleaned_prompt_output,
                'model_response': cleaned_prompt_output['data']['choices'][0]['message']['content'],
                'input_tokens': input_tokens,
                'output_tokens': output_tokens,
                'input_token_cost': input_token_cost,
                'output_token_cost': output_token_cost,
            }

            # print(full_result)

            flash('Prompt executed with success', category='info')

            return render_template("review/output.html", result=full_result)
    else:
        return render_template("review/review.html")

@app.route('/history')
def history():
    prompts = db.get_all_prompts(app.config['SETTINGS_DB'])
    request_list = []
    for prompt in prompts:
        cleaned_request = literal_eval(prompt['request'])
        cleaned_output = literal_eval(prompt['output'])
        cleaned_prompt = {
            'id': prompt['id'],
            'request': cleaned_request,
            'prompt': cleaned_request['messages'][0]['content'],
            'output': cleaned_output,
            'model_response': cleaned_output['data']['choices'][0]['message']['content'],
        }
        request_list.append(cleaned_prompt)

    return render_template("history/list.html", request_list=request_list)

@app.route('/history/<int:item_id>')
def history_detail(item_id):
    prompt = db.get_prompt(app.config['SETTINGS_DB'], item_id)
    prompt_request = prompt[1]
    prompt_output = prompt[2]

    cleaned_prompt_request = literal_eval(prompt_request)
    cleaned_prompt_output = literal_eval(prompt_output)

    input_tokens = cleaned_prompt_output['data']['usage']['input_tokens']
    output_tokens = cleaned_prompt_output['data']['usage']['output_tokens']
    print(input_tokens)
    print(output_tokens)

    input_token_cost, output_token_cost = calculate_cost(input_token_count=input_tokens, price_per_10k_tokens_input=app.config['LLM_COST_PER_10K_TOKEN_INPUT'], price_per_10k_tokens_output=app.config['LLM_COST_PER_10K_TOKEN_OUTPUT'], token_output=output_tokens)

    model_response = cleaned_prompt_output['data']['choices'][0]['message']['content']

    full_result = {
        'prompt': cleaned_prompt_request['messages'][0]['content'],
        'request': cleaned_prompt_request,
        'output': cleaned_prompt_output,
        'model_response': model_response,
        'input_tokens': input_tokens,
        'output_tokens': output_tokens,
        'input_token_cost': input_token_cost,
        'output_token_cost': output_token_cost,
    }

    return render_template("review/output.html", result=full_result)

if __name__ == "__main__":
    app.run(debug=True)
