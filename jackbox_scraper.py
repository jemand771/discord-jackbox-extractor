import re
import time

import discord
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait


class GameLoader:
    container_selector = ""
    game_image = "https://static.thenounproject.com/png/140281-200.png"

    def __init__(self, driver):
        self.driver = driver

    def wait_for_gif(self, css_selector, container=None):
        if container is None:
            container = self.driver
        WebDriverWait(container, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, css_selector)))
        while "gif" not in container.find_element_by_css_selector(css_selector).get_attribute("src"):
            time.sleep(0.01)

    @staticmethod
    def make_embed(name, png, gif, description=None):
        description = description or discord.Embed.Empty
        obj = discord.Embed(description=description, color=1)
        obj.set_author(name=name, icon_url=png)
        obj.set_image(url=gif)
        return obj

    def prepare_page(self):
        return

    def get_message(self, container):
        return

    def get_messages(self):
        self.prepare_page()
        return [{
            "embed": self.get_message(x)
        } for x in self.driver.find_elements_by_css_selector(self.container_selector)]


class GameLoaderTeeKO(GameLoader):

    container_selector = ".ui.fluid.container"
    game_image = "https://jackboxgames.b-cdn.net/wp-content/uploads/2020/04/Tee-KO-No-Text.png"

    def get_message(self, container):
        name = container.find_element_by_css_selector(".shirt-title").text
        description = None
        if ":" in name:
            description, name = name.split(": ")
        png = container.find_element_by_css_selector("img").get_attribute("src")
        gif = png.replace("shirtimage-", "anim_").replace(".png", ".gif")
        # force gif generation
        container.find_element_by_css_selector(".shirt-controls").find_elements_by_css_selector("button")[0].click()
        WebDriverWait(self.driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, ".close")))
        self.wait_for_gif(".ui.segment img")
        self.driver.find_element_by_css_selector(".close").click()
        WebDriverWait(self.driver, 10).until_not(EC.presence_of_element_located((By.CSS_SELECTOR, ".close")))
        return self.make_embed(name, png, gif, description)


class GameLoaderQuiplash3(GameLoader):

    container_selector = ".q3-matchup-artifact"
    game_image = "https://i.pinimg.com/originals/8e/e6/63/8ee66306e9ab932ad6f75c1ac389bfb3.png"

    def get_message(self, container):
        container.find_element_by_css_selector(".q3-arrow:not(.open)").click()
        img_sel = "img.image.q3-image"
        png = container.find_element_by_css_selector(img_sel).get_attribute("src")
        if ".png" not in png:
            # TODO error image?
            print("error getting static image for quiplash 3")
        self.wait_for_gif(img_sel, container)
        gif = container.find_element_by_css_selector(img_sel).get_attribute("src")
        name = container.find_element_by_css_selector(".q3-question-title").text
        return self.make_embed(name, png, gif)


class GameLoaderSTI(GameLoader):
    # TODO some parts of the embed don't load sometimes
    container_selector = ".sti-burn-artifact"
    game_image = "https://i.imgur.com/XtP9rgl.png"

    def get_message(self, container):
        container.find_element_by_css_selector(".sti-burn-arrow:not(.open)").click()
        img_sel = "img.image.sti-image"
        self.wait_for_gif(img_sel, container)
        gif = container.find_element_by_css_selector(img_sel).get_attribute("src")
        png = re.sub(r"anim(_\d+_\d+)\.gif.*", r"image\g<1>.png", gif)
        name = container.find_element_by_css_selector(".sti-burn-title").text
        description = container.find_element_by_xpath("../..").find_element_by_css_selector(".sti-round-title").text
        return self.make_embed(name, png, gif, description)

    def prepare_page(self):
        # un-open first burn artifact
        self.driver.find_element_by_css_selector(".sti-burn-arrow.open").click()
        for game_round in self.driver.find_elements_by_css_selector(".sti-round-arrow:not(.open)"):
            game_round.click()
        ActionChains(self.driver).send_keys(Keys.HOME).perform()
        time.sleep(0.5)


class ContentLoader:

    SPINNER_CLASS = ".loader.active"
    GAME_CLASSES = {
        "TeeKOGame": GameLoaderTeeKO,
        "quiplash3Game": GameLoaderQuiplash3,
        "STIGame": GameLoaderSTI
        # TODO implement more games
        # trivia murder party 2
        # champd up
        # braketeering
        # STI auto-replaces .png with .gif after a couple of seconds, 1_1 is always extended by default
        #     maybe just click all down facing arrows?
        # bracketeering also replaces png with gif, but not always? -> investigate further
    }

    def __init__(self, url):
        self.url = url
        self.title = None
        self.title_image = None
        self.game_type = url.split("/artifact/")[1].split("/")[0]
        if self.game_type not in self.GAME_CLASSES:
            raise Exception("unknown game type! maybe the bot doesn't support it yet?")
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        self.driver = webdriver.Chrome(options=chrome_options)
        self.driver.set_window_size(1920, 1080)
        self.driver.implicitly_wait(5)

        self.driver.get(url)
        try:
            WebDriverWait(self.driver, 4).until(EC.presence_of_element_located((By.CSS_SELECTOR, self.SPINNER_CLASS)))
        except TimeoutException:
            print("warning: loading spinner didn't load, proceeding anyway")

        WebDriverWait(self.driver, 60).until_not(EC.presence_of_element_located((By.CSS_SELECTOR, self.SPINNER_CLASS)))
        if "404 Page Not Found" in self.driver.page_source or self.driver.current_url != url:
            self.driver.quit()
            raise Exception("invalid link")

        self.title_image = self.GAME_CLASSES[self.game_type].game_image.replace("https://", "http://")
        self.title = self.driver.title.split(" Gallery")[0]

    def get_messages(self):
        return self.GAME_CLASSES[self.game_type](self.driver).get_messages()
