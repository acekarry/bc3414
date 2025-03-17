def validate_input(prompt, expected_type, error_message="Invalid input, try again: "):
    while True:
        try:
            return expected_type(input(prompt))
        except ValueError:
            print(error_message)
