import sys, soundfile as sf
from kokoro_onnx import Kokoro
A="/home/user/smoke-testing-sci/o-says-oh/assets/"
k=Kokoro(A+"kokoro-v1.0.onnx",A+"voices-v1.0.bin")
lines={
 1:"Is it scary... or fun-scary? Let's find out!",
 2:"A mask? Ooh... fun-scary!",
 3:"A dark hallway? Hmm... that feels too scary.",
 4:"A spooky sound? Boo! ... Hee hee! Fun-scary!",
 5:"A friend in a costume? Fun-scary!",
 6:"It's okay to take the mask off. Halloween can feel fun... or too scary. Both are okay.",
}
for i,t in lines.items():
    s,sr=k.create(t,voice="af_heart",speed=0.95,lang="en-us")
    sf.write(f"/home/user/smoke-testing-sci/o-says-oh/build/vo/raw{i}.wav",s,sr)
    print(i,len(s)/sr)
