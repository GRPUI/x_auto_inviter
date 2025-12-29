def get_tokens_from_txt(file_path):
    with open(file_path, "r", encoding="utf-8") as file:
        tokens = file.readlines()
        tokens = [token.strip() for token in tokens]
        return tokens


def get_users_from_txt(file_path):
    with open(file_path, "r", encoding="utf-8") as file:
        users = file.readlines()
        users = [user.strip() for user in users]
        return users
