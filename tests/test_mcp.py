import asyncio

from mcp import Client

from wow_knowledge.mcp_server import mcp


def test_mcp_lists_all_required_tools():
    async def check():
        async with Client(mcp) as client:
            tools = await client.list_tools()
            names = {tool.name for tool in tools.tools}
            assert {"wow_search_knowledge", "wow_ingest_url", "wow_refresh_sources",
                    "wow_get_character", "wow_save_character", "wow_source_status"} <= names

    asyncio.run(check())
