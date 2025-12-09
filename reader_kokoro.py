from kokoro import KPipeline
from IPython.display import display, Audio
import soundfile as sf
import torch


class Reader:
    def __init__(self):
        self.pipeline = KPipeline(lang_code='a')

    def generate(self, text):
        generator = self.pipeline(text, voice='af_heart')
        for i, (gs, ps, audio) in enumerate(generator):
            print(i, gs, ps)
            display(Audio(data=audio, rate=24000, autoplay=i==0))
            sf.write(f'{i}.wav', audio, 24000)

    

        