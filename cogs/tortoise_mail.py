import discord
from discord.ext import commands
from asyncio import TimeoutError
from typing import Union


mod_mail_report_channel_id = 581139962611892229
code_submissions_channel_id = 581139962611892229
bug_reports_channel_id = 581139962611892229


class UnsupportedFileExtension(Exception):
    pass


class UnsupportedFileEncoding(ValueError):
    pass


class ModMail(commands.Cog):
    """
    TODO:
    Check if emoji id error deleted.
    Check if user blocks dms.
    Add timeout so user can't spam.
    Prettify with embeds.
    """
    def __init__(self, bot):
        self.bot = bot
        self.active_mod_mails = {}
        self.pending_mod_mails = set()
        self.active_event_submissions = set()
        self.active_bug_reports = set()
        # Keys are custom emoji IDs, subdict message is the message appearing in the bot DM and callable
        # is the method to call when that option is selected.
        self._options = {620502308815503380: {"message": "Mod mail", "callable": self.create_mod_mail},
                         611403448750964746: {"message": "Event submission", "callable": self.create_event_submission},
                         610825682070798359: {"message": "Bug report", "callable": self.create_bug_report}}

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        user_id = payload.user_id
        if user_id == self.bot.user.id:
            # Ignore the bot
            return
        elif self.is_any_session_active(user_id):
            return

        for emoji_id, sub_dict in self._options.items():
            emoji = self.bot.get_emoji(emoji_id)
            if emoji == payload.emoji:
                user = self.bot.get_user(user_id)
                await sub_dict["callable"](user)
                break

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author == self.bot.user:
            return
        elif message.guild is not None:
            # Functionality only active in DMs
            return

        if self.is_any_session_active(message.author.id):
            return
        else:
            await self.send_dm_options(output=message.author)

    async def send_dm_options(self, *, output):
        for emoji_id, sub_dict in self._options.items():
            dm_msg = await output.send(sub_dict["message"])
            await dm_msg.add_reaction(self.bot.get_emoji(emoji_id))

    def is_any_session_active(self, user_id: int) -> bool:
        # If the mod mail or anything else is active don't clutter the active session
        return any(user_id in active for active in (self.active_mod_mails,
                                                    self.active_event_submissions,
                                                    self.active_bug_reports))

    async def create_mod_mail(self, user: discord.User):
        if user.id in self.pending_mod_mails:
            await user.send("You already have a pending mod mail, please be patient.")
            return

        mod_mail_report_channel = self.bot.get_channel(mod_mail_report_channel_id)
        await mod_mail_report_channel.send(f"User `{user.name}` ID:{user.id} submitted for mod mail.")
        self.pending_mod_mails.add(user.id)
        await user.send("Mod mail was sent to admins, please wait for on of the admins to accept.")

    async def create_event_submission(self, user: discord.User):
        user_reply = await self._wait_for(self.active_event_submissions, user)
        if user_reply is None:
            return

        try:
            possible_attachment = await self.get_message_txt_attachment(user_reply)
        except (UnsupportedFileExtension, UnsupportedFileEncoding) as e:
            await user.send(f"Error: {e} , canceling.")
            self.active_event_submissions.remove(user.id)
            return

        event_submission = user_reply.content if possible_attachment is None else possible_attachment
        if len(event_submission) < 10:
            await user.send("Too short - seems invalid, canceling.")
            self.active_event_submissions.remove(user.id)
            return

        code_submissions_channel = self.bot.get_channel(code_submissions_channel_id)
        await code_submissions_channel.send(f"User `{user.name}` ID:{user.id} submitted code submission: "
                                            f"{event_submission}")
        await user.send("Event submission successfully submitted.")
        self.active_event_submissions.remove(user.id)

    async def create_bug_report(self, user: discord.User):
        user_reply = await self._wait_for(self.active_bug_reports, user)
        if user_reply is None:
            return

        try:
            possible_attachment = await self.get_message_txt_attachment(user_reply)
        except (UnsupportedFileExtension, UnsupportedFileEncoding) as e:
            await user.send(f"Error: {e} , canceling.")
            self.active_bug_reports.remove(user.id)
            return

        bug_report = user_reply.content if possible_attachment is None else possible_attachment
        if len(bug_report) < 10:
            await user.send("Too short - seems invalid, canceling.")
            self.active_bug_reports.remove(user.id)
            return

        bug_report_channel = self.bot.get_channel(bug_reports_channel_id)
        await bug_report_channel.send(f"User `{user.name}` ID:{user.id} submitted bug report: {bug_report}")
        await user.send("Bug report successfully submitted, thank you.")
        self.active_bug_reports.remove(user.id)

    async def _wait_for(self, container: set, user: discord.User) -> Union[discord.Message, None]:
        """
        Simple custom wait_for that waits for user reply for 5 minutes and has ability to cancel the wait and
        deal with errors.
        :param container: set, container holding active user sessions by having their IDs in it.
        :param user: Discord user to wait reply from
        :return: Union[Message, None] message representing user reply, can be none representing invalid reply.
        """
        def check(msg):
            return msg.guild is None and msg.author == user

        container.add(user.id)
        await user.send("Reply with message, link to paste service or uploading utf-8 `.txt` file.\n"
                        "You have 5m, type `cancel` to cancel right away.")

        try:
            user_reply = await self.bot.wait_for("message", check=check, timeout=300)
        except TimeoutError:
            await user.send("You took too long to reply.")
            container.remove(user.id)
            return

        if user_reply.content.lower() == "cancel":
            await user.send("Successfully canceled.")
            container.remove(user.id)
            return

        return user_reply

    @classmethod
    async def get_message_txt_attachment(cls, message: discord.Message) -> Union[str, None]:
        """
        Only supports .txt file attachments and only utf-8 encoding supported.
        :param message: message object to extract attachment from.
        :return: Union[str, None]
        :raise UnsupportedFileExtension: If file type is other than .txt
        :raise UnicodeDecodeError: If decoding the file fails
        """
        try:
            attachment = message.attachments[0]
        except IndexError:
            return None

        if not attachment.filename.endswith(".txt"):
            raise UnsupportedFileExtension("Only `.txt` files supported")

        try:
            content = (await attachment.read()).decode("utf-8")
        except UnicodeDecodeError:
            raise UnsupportedFileEncoding("Unsupported file encoding, please only use utf-8")

        return content


def setup(bot):
    bot.add_cog(ModMail(bot))
