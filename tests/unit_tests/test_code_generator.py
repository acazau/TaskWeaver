import os

from injector import Injector

from taskweaver.config.config_mgt import AppConfigSource
from taskweaver.logging import LoggingModule
from taskweaver.memory.plugin import PluginModule


def test_compose_prompt():
    app_injector = Injector(
        [PluginModule, LoggingModule],
    )
    app_config = AppConfigSource(
        config={
            "app_dir": os.path.dirname(os.path.abspath(__file__)),
            "llm.api_key": "this_is_not_a_real_key",  # pragma: allowlist secret
            "code_generator.prompt_compression": True,
            "code_generator.prompt_file_path": os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "data/prompts/generator_prompt.yaml",
            ),
        },
    )
    app_injector.binder.bind(AppConfigSource, to=app_config)

    from taskweaver.code_interpreter.code_generator import CodeGenerator
    from taskweaver.memory import Attachment, Memory, Post, Round

    code_generator = app_injector.create_object(CodeGenerator)

    code1 = (
        "df = pd.DataFrame(np.random.rand(10, 2), columns=['DATE', 'VALUE'])\n"
        'descriptions = [("sample_code_description", "Sample code has been generated to get a dataframe `df` \n'
        "with 10 rows and 2 columns: 'DATE' and 'VALUE'\")]"
    )
    post1 = Post.create(
        message="create a dataframe",
        send_from="Planner",
        send_to="CodeInterpreter",
        attachment_list=[],
    )
    post2 = Post.create(
        message="A dataframe `df` with 10 rows and 2 columns: 'DATE' and 'VALUE' has been generated.",
        send_from="CodeInterpreter",
        send_to="Planner",
        attachment_list=[],
    )
    post2.add_attachment(
        Attachment.create(
            "thought",
            "{ROLE_NAME} sees the user wants generate a DataFrame.",
        ),
    )
    post2.add_attachment(
        Attachment.create(
            "thought",
            "{ROLE_NAME} sees all required Python libs have been imported, so will not generate import codes.",
        ),
    )
    post2.add_attachment(Attachment.create("python", code1))
    post2.add_attachment(Attachment.create("execution_status", "SUCCESS"))
    post2.add_attachment(
        Attachment.create(
            "execution_result",
            "A dataframe `df` with 10 rows and 2 columns: 'DATE' and 'VALUE' has been generated.",
        ),
    )

    round1 = Round.create(user_query="hello", id="round-1")
    round1.add_post(post1)
    round1.add_post(post2)

    round2 = Round.create(user_query="hello again", id="round-2")
    post3 = Post.create(
        message="what is the data range",
        send_from="Planner",
        send_to="CodeInterpreter",
        attachment_list=[],
    )
    post4 = Post.create(
        message="The data range for the 'VALUE' column is 0.94",
        send_from="CodeInterpreter",
        send_to="Planner",
        attachment_list=[],
    )
    post4.add_attachment(
        Attachment.create(
            "thought",
            "{ROLE_NAME} understands the user wants to find the data range for the DataFrame.",
        ),
    )
    post4.add_attachment(
        Attachment.create(
            "thought",
            "{ROLE_NAME} will generate code to calculate the data range of the 'VALUE' column since it is the "
            "only numeric column.",
        ),
    )
    post4.add_attachment(
        Attachment.create(
            "python",
            (
                "min_value = df['VALUE'].min()\n"
                "max_value = df['VALUE'].max()\n"
                "data_range = max_value - min_value\n"
                "descriptions = [\n"
                '("min_value", f"The minimum value in the \'VALUE\' column is {min_value:.2f}"),\n'
                '("max_value", f"The maximum value in the \'VALUE\' column is {max_value:.2f}"),\n'
                '("data_range", f"The data range for the \'VALUE\' column is {data_range:.2f}")\n'
                "]"
            ),
        ),
    )
    post4.add_attachment(Attachment.create("execution_status", "SUCCESS"))
    post4.add_attachment(
        Attachment.create(
            "execution_result",
            "The minimum value in the 'VALUE' column is 0.05;The "
            "maximum value in the 'VALUE' column is 0.99;The "
            "data range for the 'VALUE' column is 0.94",
        ),
    )
    round2.add_post(post3)
    round2.add_post(post4)

    round3 = Round.create(user_query="hello again", id="round-3")
    post5 = Post.create(
        message="what is the max value?",
        send_from="Planner",
        send_to="CodeInterpreter",
        attachment_list=[],
    )
    round3.add_post(post5)

    memory = Memory(session_id="session-1")
    memory.conversation.add_round(round1)
    memory.conversation.add_round(round2)
    memory.conversation.add_round(round3)

    messages = code_generator.compose_prompt(
        rounds=memory.conversation.rounds,
        plugins=code_generator.get_plugin_pool(),
    )

    assert messages[0]["role"] == "system"
    assert messages[0]["content"].startswith("## On conversations:")
    assert messages[1]["role"] == "user"
    assert messages[1]["content"] == (
        "==============================\n"
        "## Conversation Start\n"
        "\n"
        "### Context Summary\n"
        "The context summary of previous rounds and the variables that "
        "ProgramApe can refer to:\n"
        "None\n"
        "\n"
        "### Plugin Functions\n"
        "The functions can be directly called without importing:\n"
        "None\n"
        "-----------------------------\n"
        "# Feedback of the code in the last round (None if no feedback):\n"
        "None\n"
        "\n"
        "# Request from the User in this round:\n"
        "create a dataframe"
    )
    assert messages[2]["role"] == "assistant"
    assert messages[2]["content"] == (
        '{"response": [{"type": "thought", "content": "ProgramApe sees the user wants '
        'generate a DataFrame."}, {"type": "thought", "content": "ProgramApe sees all '
        "required Python libs have been imported, so will not generate import "
        'codes."}, {"type": "python", "content": "df = pd.DataFrame(np.random.rand(10, '
        "2), columns=['DATE', 'VALUE'])\\ndescriptions = "
        '[(\\"sample_code_description\\", \\"Sample code has been generated to get a '
        "dataframe `df` \\nwith 10 rows and 2 columns: 'DATE' and "
        "'VALUE'\\\")]\"}]}"
    )

    assert messages[5]["role"] == "user"
    assert messages[5]["content"] == (
        "-----------------------------\n"
        "# Feedback of the code in the last round (None if no feedback):\n"
        "## Execution\n"
        "Your code has been executed successfully with the following result:\n"
        "The minimum value in the 'VALUE' column is 0.05;The maximum value in the "
        "'VALUE' column is 0.99;The data range for the 'VALUE' column is 0.94\n"
        "\n"
        "\n"
        "# Request from the User in this round:\n"
        "what is the max value?\n"
        "Please follow the instructions below to complete the task:\n"
        "- ProgramApe can refer to intermediate variables in the generated code from "
        "previous successful rounds and the context summary in the current "
        "Conversation, \n"
        "- ProgramApe should not refer to any information from failed rounds, rounds "
        "that have not been executed, or previous Conversations.\n"
        "- ProgramApe put all the result variables in the last line of the code.\n"
        "- ProgramApe must not import the plugins and otherwise the code will be "
        "failed to execute.\n"
    )


def test_compose_prompt_with_plugin():
    app_injector = Injector(
        [PluginModule, LoggingModule],
    )
    app_config = AppConfigSource(
        config={
            "app_dir": os.path.dirname(os.path.abspath(__file__)),
            "llm.api_key": "test_key",  # pragma: allowlist secret
            "code_generator.prompt_compression": True,
            "code_generator.prompt_file_path": os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "data/prompts/generator_prompt.yaml",
            ),
            "plugin.base_path": os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "data/plugins",
            ),
        },
    )
    app_injector.binder.bind(AppConfigSource, to=app_config)

    from taskweaver.code_interpreter.code_generator import CodeGenerator
    from taskweaver.memory import Attachment, Memory, Post, Round

    code_generator = app_injector.create_object(CodeGenerator)

    code1 = (
        "df = pd.DataFrame(np.random.rand(10, 2), columns=['DATE', 'VALUE'])\n"
        'descriptions = [("sample_code_description", "Sample code has been generated to get a dataframe `df` \n'
        "with 10 rows and 2 columns: 'DATE' and 'VALUE'\")]"
    )
    post1 = Post.create(
        message="create a dataframe",
        send_from="Planner",
        send_to="CodeInterpreter",
        attachment_list=[],
    )
    post2 = Post.create(
        message="A dataframe `df` with 10 rows and 2 columns: 'DATE' and 'VALUE' has been generated.",
        send_from="CodeInterpreter",
        send_to="Planner",
        attachment_list=[],
    )
    post2.add_attachment(
        Attachment.create(
            "thought",
            "{ROLE_NAME} sees the user wants generate a DataFrame.",
        ),
    )
    post2.add_attachment(
        Attachment.create(
            "thought",
            "{ROLE_NAME} sees all required Python libs have been imported, so will not generate import codes.",
        ),
    )
    post2.add_attachment(Attachment.create("python", code1))
    post2.add_attachment(Attachment.create("execution_status", "SUCCESS"))
    post2.add_attachment(
        Attachment.create(
            "execution_result",
            "A dataframe `df` with 10 rows and 2 columns: 'DATE' and 'VALUE' has been generated.",
        ),
    )

    round1 = Round.create(user_query="hello", id="round-1")
    round1.add_post(post1)
    round1.add_post(post2)

    memory = Memory(session_id="session-1")
    memory.conversation.add_round(round1)

    messages = code_generator.compose_prompt(
        rounds=memory.conversation.rounds,
        plugins=code_generator.get_plugin_pool(),
    )

    assert messages[1]["role"] == "user"
    assert "sql_pull_data" in messages[1]["content"]
    assert "anomaly_detection" in messages[1]["content"]
    assert "klarna_search" in messages[1]["content"]
    assert "paper_summary" in messages[1]["content"]


def test_compose_prompt_with_plugin_only():
    app_injector = Injector(
        [PluginModule, LoggingModule],
    )
    app_config = AppConfigSource(
        config={
            "app_dir": os.path.dirname(os.path.abspath(__file__)),
            "llm.api_key": "test_key",  # pragma: allowlist secret
            "code_generator.prompt_compression": True,
            "code_generator.prompt_file_path": os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "data/prompts/generator_prompt.yaml",
            ),
            "plugin.base_path": os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "data/plugins",
            ),
            "code_generator.example_base_path": os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "data/examples/codeinterpreter_examples",
            ),
        },
    )
    app_injector.binder.bind(AppConfigSource, to=app_config)

    from taskweaver.code_interpreter.code_generator import CodeGenerator
    from taskweaver.memory import Attachment, Memory, Post, Round

    code_generator = app_injector.get(CodeGenerator)

    code_generator.configure_verification(
        code_verification_on=True,
        plugin_only=True,
        allowed_modules=[],
    )
    code_generator.configure_verification(code_verification_on=True, plugin_only=True)

    code1 = (
        "df = pd.DataFrame(np.random.rand(10, 2), columns=['DATE', 'VALUE'])\n"
        'descriptions = [("sample_code_description", "Sample code has been generated to get a dataframe `df` \n'
        "with 10 rows and 2 columns: 'DATE' and 'VALUE'\")]"
    )
    post1 = Post.create(
        message="create a dataframe",
        send_from="Planner",
        send_to="CodeInterpreter",
        attachment_list=[],
    )
    post2 = Post.create(
        message="A dataframe `df` with 10 rows and 2 columns: 'DATE' and 'VALUE' has been generated.",
        send_from="CodeInterpreter",
        send_to="Planner",
        attachment_list=[],
    )
    post2.add_attachment(
        Attachment.create(
            "thought",
            "{ROLE_NAME} sees the user wants generate a DataFrame.",
        ),
    )
    post2.add_attachment(
        Attachment.create(
            "thought",
            "{ROLE_NAME} sees all required Python libs have been imported, so will not generate import codes.",
        ),
    )
    post2.add_attachment(Attachment.create("python", code1))
    post2.add_attachment(Attachment.create("execution_status", "SUCCESS"))
    post2.add_attachment(
        Attachment.create(
            "execution_result",
            "A dataframe `df` with 10 rows and 2 columns: 'DATE' and 'VALUE' has been generated.",
        ),
    )

    round1 = Round.create(user_query="hello", id="round-1")
    round1.add_post(post1)
    round1.add_post(post2)

    memory = Memory(session_id="session-1")
    memory.conversation.add_round(round1)

    messages = code_generator.compose_prompt(
        rounds=memory.conversation.rounds,
        plugins=code_generator.get_plugin_pool(),
    )

    assert "read_csv" in messages[1]["content"]
    assert "write_csv" in messages[1]["content"]
    assert "This is the feedback" in messages[3]["content"]
    assert "Execution" in messages[3]["content"]
    assert "Verification" in messages[3]["content"]

    assert "sql_pull_data" in messages[4]["content"]
    assert "anomaly_detection" in messages[4]["content"]
    assert "klarna_search" in messages[4]["content"]
    assert "paper_summary" in messages[4]["content"]


def test_compose_prompt_with_not_plugin_only():
    app_injector = Injector(
        [PluginModule, LoggingModule],
    )
    app_config = AppConfigSource(
        config={
            "app_dir": os.path.dirname(os.path.abspath(__file__)),
            "llm.api_key": "test_key",  # pragma: allowlist secret
            "code_generator.prompt_compression": True,
            "code_generator.prompt_file_path": os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "data/prompts/generator_prompt.yaml",
            ),
            "plugin.base_path": os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "data/plugins",
            ),
            "code_generator.example_base_path": os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "data/examples/codeinterpreter_examples",
            ),
        },
    )
    app_injector.binder.bind(AppConfigSource, to=app_config)

    from taskweaver.code_interpreter.code_generator import CodeGenerator
    from taskweaver.memory import Attachment, Memory, Post, Round

    code_generator = app_injector.get(CodeGenerator)

    code1 = (
        "df = pd.DataFrame(np.random.rand(10, 2), columns=['DATE', 'VALUE'])\n"
        'descriptions = [("sample_code_description", "Sample code has been generated to get a dataframe `df` \n'
        "with 10 rows and 2 columns: 'DATE' and 'VALUE'\")]"
    )
    post1 = Post.create(
        message="create a dataframe",
        send_from="Planner",
        send_to="CodeInterpreter",
        attachment_list=[],
    )
    post2 = Post.create(
        message="A dataframe `df` with 10 rows and 2 columns: 'DATE' and 'VALUE' has been generated.",
        send_from="CodeInterpreter",
        send_to="Planner",
        attachment_list=[],
    )
    post2.add_attachment(
        Attachment.create(
            "thought",
            "{ROLE_NAME} sees the user wants generate a DataFrame.",
        ),
    )
    post2.add_attachment(
        Attachment.create(
            "thought",
            "{ROLE_NAME} sees all required Python libs have been imported, so will not generate import codes.",
        ),
    )
    post2.add_attachment(Attachment.create("python", code1))
    post2.add_attachment(Attachment.create("execution_status", "SUCCESS"))
    post2.add_attachment(
        Attachment.create(
            "execution_result",
            "A dataframe `df` with 10 rows and 2 columns: 'DATE' and 'VALUE' has been generated.",
        ),
    )

    round1 = Round.create(user_query="hello", id="round-1")
    round1.add_post(post1)
    round1.add_post(post2)

    memory = Memory(session_id="session-1")
    memory.conversation.add_round(round1)

    messages = code_generator.compose_prompt(
        rounds=memory.conversation.rounds,
        plugins=code_generator.get_plugin_pool(),
    )

    assert "read_csv" not in messages[1]["content"]
    assert "write_csv" not in messages[1]["content"]
    assert "sql_pull_data" not in messages[1]["content"]
    assert "anomaly_detection" not in messages[1]["content"]
    assert "klarna_search" not in messages[1]["content"]
    assert "paper_summary" not in messages[1]["content"]

    assert "sql_pull_data" in messages[13]["content"]
    assert "anomaly_detection" in messages[13]["content"]
    assert "klarna_search" in messages[13]["content"]
    assert "paper_summary" in messages[13]["content"]


def test_code_correction_prompt():
    app_injector = Injector(
        [PluginModule, LoggingModule],
    )
    app_config = AppConfigSource(
        config={
            "app_dir": os.path.dirname(os.path.abspath(__file__)),
            "llm.api_key": "test_key",  # pragma: allowlist secret
            "code_generator.prompt_file_path": os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "data/prompts/generator_prompt.yaml",
            ),
        },
    )
    app_injector.binder.bind(AppConfigSource, to=app_config)

    from taskweaver.code_interpreter.code_generator import CodeGenerator
    from taskweaver.memory import Attachment, Memory, Post, Round

    prompt_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "data/prompts/generator_prompt.yaml",
    )
    code_generator = app_injector.create_object(CodeGenerator)

    code1 = (
        "df = pd.DataFrame(np.random.rand(10, 2), columns=['DATE', 'VALUE'])\n"
        'descriptions = [("sample_code_description", "Sample code has been generated to get a dataframe `df` \n'
        "with 10 rows and 2 columns: 'DATE' and 'VALUE'\")]"
    )
    post1 = Post.create(
        message="create a dataframe",
        send_from="Planner",
        send_to="CodeInterpreter",
        attachment_list=[],
    )
    post2 = Post.create(
        message="A dataframe `df` with 10 rows and 2 columns: 'DATE' and 'VALUE' has been generated.",
        send_from="CodeInterpreter",
        send_to="CodeInterpreter",
        attachment_list=[],
    )
    post2.add_attachment(
        Attachment.create(
            "thought",
            "{ROLE_NAME} sees the user wants generate a DataFrame.",
        ),
    )
    post2.add_attachment(
        Attachment.create(
            "thought",
            "{ROLE_NAME} sees all required Python libs have been imported, so will not generate import codes.",
        ),
    )
    post2.add_attachment(Attachment.create("python", code1))
    post2.add_attachment(Attachment.create("execution_status", "FAILURE"))
    post2.add_attachment(
        Attachment.create(
            "execution_result",
            "The code failed to execute. Please check the code and try again.",
        ),
    )
    post2.add_attachment(
        Attachment.create("revise_message", "Please check the code and try again."),
    )

    round1 = Round.create(user_query="hello", id="round-1")
    round1.add_post(post1)
    round1.add_post(post2)

    memory = Memory(session_id="session-1")
    memory.conversation.add_round(round1)

    messages = code_generator.compose_prompt(
        rounds=memory.conversation.rounds,
        plugins=code_generator.get_plugin_pool(),
    )

    assert len(messages) == 4
    assert messages[3]["role"] == "user"
    assert messages[3]["content"] == (
        "-----------------------------\n"
        "# Feedback of the code in the last round (None if no feedback):\n"
        "## Execution\n"
        "Your code has failed to execute with the following error:\n"
        "The code failed to execute. Please check the code and try again.\n"
        "\n"
        "\n"
        "# Request from the User in this round:\n"
        "Please check the code and try again.\n"
        "Please follow the instructions below to complete the task:\n"
        "- ProgramApe can refer to intermediate variables in the generated code from "
        "previous successful rounds and the context summary in the current "
        "Conversation, \n"
        "- ProgramApe should not refer to any information from failed rounds, rounds "
        "that have not been executed, or previous Conversations.\n"
        "- ProgramApe put all the result variables in the last line of the code.\n"
        "- ProgramApe must not import the plugins and otherwise the code will be "
        "failed to execute.\n"
    )
