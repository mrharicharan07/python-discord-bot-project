import os

MAIN_BOT_KEY = os.getenv('ONBOARDING_MAIN_BOT_KEY', '')
CLIENT_ID = os.getenv('ONBOARDING_CLIENT_ID', '0')
GUILD_ID = os.getenv('ONBOARDING_GUILD_ID', '0')
ONBOARDING_CHANNEL_ID = os.getenv('ONBOARDING_CHANNEL_ID', '0')

ONBOARDING_QUESTIONS = [
    {
        'key': 'platform',
        'prompt': 'Which platform do you mainly use?',
        'placeholder': 'Choose your platform',
        'options': [
            {
                'value': 'pc',
                'label': 'PC',
                'description': 'Assign the PC role',
                'role_id': 0,
            },
            {
                'value': 'mobile',
                'label': 'Mobile',
                'description': 'Assign the Mobile role',
                'role_id': 0,
            },
        ],
    },
]

COMPLETION_ROLE_ID = 0
