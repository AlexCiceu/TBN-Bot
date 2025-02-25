import time
from disnake import Member, ApplicationCommandInteraction
from disnake.ext import commands
from sqlalchemy import extract
from config import Configuration
from datetime import datetime, timedelta
from database import database_session, TbnMember
import openai
import os

from database.tbnbotdatabase import TbnMemberAudit

birthday_input_format = '%d/%m/%Y'
birthday_output_format = '%d %B'

class Birthdays(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db_session = database_session()

    # Register as slash command - pass in Guild ID so command changes propagate immediately
    @commands.slash_command(guild_ids=[Configuration.instance().GUILD_ID], name="setbirthday", description="Set your birthday")
    async def set_birthday(self, interaction: ApplicationCommandInteraction, birthday: str):
        """
        Set your birthday so you can be congratulated in the future.

        Parameters
        ----------
        birthday: dd/mm or dd/mm/yyyy format.
        """        
        date = datetime.strptime(birthday if len(birthday) == 10 else birthday[0:5] + '/1900', birthday_input_format)

        changed_member = TbnMember(interaction.author.id, date)        
        self.db_session.merge(changed_member)        
        self.db_session.add(TbnMemberAudit(changed_member))
        
        self.db_session.commit()

        await interaction.response.send_message(f"{interaction.author.mention}, your birthday is registered as {date.date().strftime(birthday_output_format)}", ephemeral=True)

    @commands.slash_command(guild_ids=[Configuration.instance().GUILD_ID], name="upcomingbirthdays", description="See all birthdays in the next 31 days.")
    async def upcoming_birthdays(self, interaction: ApplicationCommandInteraction):
        # TODO figure out how to filter this within the sqlalchemy query
        all_members = self.db_session.query(TbnMember)\
            .filter(TbnMember.birthday != None)\
            .order_by(TbnMember.birthday.asc()).all()
        
        def is_upcoming_birthday(member: TbnMember):
            birthday = datetime(year = datetime.now().year, month = member.birthday.month, day = member.birthday.day)
            return birthday > datetime.now() and birthday < datetime.now() + timedelta(days = 31)

        upcoming_birthday_bois = filter(is_upcoming_birthday, all_members)

        await interaction.response.send_message(f"Upcoming birthdays in the next 31 days:\n{os.linesep.join([f'<@!{member.id}>: {member.birthday.strftime(birthday_output_format)}' for member in upcoming_birthday_bois])}", ephemeral=True)

    @commands.slash_command(guild_ids=[Configuration.instance().GUILD_ID], name="removebirthday", description="Remove your birthday.")
    async def remove_birthday(self, interaction: ApplicationCommandInteraction):
        self.db_session.query(TbnMember).filter(TbnMember.id == interaction.author.id).first().birthday = None
        self.db_session.commit()

        await interaction.response.send_message(f"{interaction.author.mention}, your birthday has been removed.", ephemeral=True)

    @commands.slash_command(guild_ids=[Configuration.instance().GUILD_ID], name="showbirthday", description="Show your birthday, just in case you forgot.")
    async def show_birthday(self, interaction: ApplicationCommandInteraction):
        birthday_boi = self.db_session.query(TbnMember).filter(TbnMember.id == interaction.author.id).first()
        await interaction.response.send_message(f"{interaction.author.mention}, your birthday is registered as {birthday_boi.birthday.strftime(birthday_output_format)}", ephemeral=True)

    async def notify_birthdays(self):
        birthday_bois = self.db_session.query(TbnMember)\
            .filter(extract('month', TbnMember.birthday) == datetime.now().month)\
            .filter(extract('day', TbnMember.birthday) == datetime.now().day)\
            .all()

        user_message_1 = f"""You are an announcer for birthdays of members of a Discord community called 'The Biscuit Network' or TBN for short.  
        The announcement should contain a short paragraph for each user referencing by their ID. 
        For example, for a user with ID 186222231125360641 you could say: 
        "Hello gang! It's one of our esteemed members' birthday today! 
        Please congratulate <@!186222231125360641> on their birthday! <@!186222231125360641>"
        Followed by a short message wishing them a happy birthday and expressing how much they mean to the community. This message should be funny, complimentary and flirtatious.
        Include many emoji relevant to birthday celebrations such as 🎂, 🥳, 🎉, ❤. Make sure to format it neatly by starting a new paragraph for each user. 
        If there are multiple users with birthdays on the same day, make sure to mention all of them in the announcement, but each of their messages should be unique.
        Be creative in your response, but make sure to NEVER mention a User ID unless it's surrounded by <@! and > in the form of a Discord mention such as <@!186222231125360641>! 
        Respond "Ok." to confirm you understand.
        """

        assistant_message_1 = "Ok."

        user_message_2 = F"There are {len(birthday_bois)} birthdays today, their User IDs are {', '.join([str(member.id) for member in birthday_bois])}. Please write the announcement."

        announcement = ""

        for attempt in range(1, 6):
            try:
                print(f"Attempt #{attempt}...")
                completion = completion = openai.ChatCompletion.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "user", "content": user_message_1},
                        {"role": "assistant", "content": assistant_message_1},
                        {"role": "user", "content": user_message_2}
                    ]
                )

                announcement = completion.choices[0].message.content
                break
            except:
                print(f"Failed.")
                time.sleep(5)
                continue

        if announcement == "":
            announcement = (
                f'Good morning gang, today is <@!{birthday_bois[0].id}>\'s birthday! Happy birthday <@!{birthday_bois[0].id}>! :partying_face: :birthday: :partying_face:'
                if len(birthday_bois) == 1
                else f'Good morning gang, we have _multiple_ birthdays today! Happy birthday to {", ".join([f"<@!{member.id}>" for member in birthday_bois])}! :partying_face: :birthday: :partying_face:'
            )

        await self.bot.get_channel(Configuration.instance().BIRTHDAYS_CHANNEL_ID).send(announcement)

# Called by bot.load_extension in main
def setup(bot: commands.Bot):
    bot.add_cog(Birthdays(bot))