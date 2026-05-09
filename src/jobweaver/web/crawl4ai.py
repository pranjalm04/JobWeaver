from crawl4ai import BrowserConfig, CrawlerRunConfig, CacheMode


def build_browser_config() -> BrowserConfig:
    return BrowserConfig(
        browser_type="chromium",
        headless=True,
        viewport={"width": 1920, "height": 1080},
        user_agent=(
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "Chrome/116.0.0.0 Safari/537.36"
        ),
    )


def build_run_config() -> CrawlerRunConfig:
    return CrawlerRunConfig(
        wait_until="domcontentloaded",
        excluded_tags=["style"],
        exclude_external_links=False,
        cache_mode=CacheMode.DISABLED,
        process_iframes=True,
        remove_overlay_elements=True,
        exclude_external_images=True,
        exclude_social_media_links=True,
        check_robots_txt=False,
        verbose=False,
        log_console=False,
    )

