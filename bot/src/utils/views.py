"""Base View yang tidak bikin bingung saat timeout.

Masalah yang diperbaiki: `discord.ui.View.on_timeout` bawaan hanya menonaktifkan
tombol di memori — pesan yang sudah dikirim tetap menampilkan tombol seolah
bisa diklik, padahal sudah mati ("interaction failed" kalau dipencet).
`TimeoutSafeView` menyimpan referensi pesan dan meng-update tampilannya
(tombol jadi abu-abu/disabled) saat timeout.
"""
import discord


class TimeoutSafeView(discord.ui.View):
    """View yang meng-update pesannya sendiri saat timeout."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.message: discord.Message | None = None

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                # pesan sudah dihapus / tidak bisa di-edit — abaikan saja
                pass


async def bind_view_message(ctx, view: TimeoutSafeView, sent) -> None:
    """Simpan referensi pesan ke view agar `on_timeout` bisa meng-update-nya.

    `sent` adalah hasil `await ctx.send(...)`. Untuk hybrid command yang
    dipanggil via slash, `ctx.send` kadang mengembalikan `None` — kalau begitu
    fallback ke `interaction.original_response()`.
    """
    msg = sent
    if msg is None and ctx.interaction is not None:
        try:
            msg = await ctx.interaction.original_response()
        except discord.HTTPException:
            msg = None
    view.message = msg
