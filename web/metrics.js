/* Transparent diagnostics on equally resized sRGB images; never an aesthetic score. */
(function(root) {
  function measure(pixels, width, height, darkThreshold=5, brightThreshold=250) {
    if (width < 3 || height < 3 || pixels.length !== width * height * 4) throw new Error('图像尺寸无效');
    if(!Number.isFinite(darkThreshold)||!Number.isFinite(brightThreshold)||darkThreshold<0||brightThreshold>255||darkThreshold>=brightThreshold)throw new Error('阈值必须满足 0 ≤ 暗部 < 高光 ≤ 255');
    const gray = new Float64Array(width * height), hist = Array(16).fill(0);
    let sum=0, dark=0, bright=0, red=0, blue=0;
    for (let i=0;i<gray.length;i++) {
      const j=i*4, y=.2126*pixels[j]+.7152*pixels[j+1]+.0722*pixels[j+2];
      gray[i]=y;sum+=y;dark+=y<=darkThreshold;bright+=y>=brightThreshold;red+=pixels[j];blue+=pixels[j+2];
      hist[Math.min(15,Math.floor(y/16))]++;
    }
    let lap=0,lap2=0,n=0;
    for(let y=1;y<height-1;y++)for(let x=1;x<width-1;x++){
      const i=y*width+x,v=gray[i-1]+gray[i+1]+gray[i-width]+gray[i+width]-4*gray[i];
      lap+=v;lap2+=v*v;n++;
    }
    return {luma:sum/gray.length,dark:100*dark/gray.length,bright:100*bright/gray.length,
      laplacian:Math.max(0,lap2/n-(lap/n)**2),redBlue:(red-blue)/gray.length,histogram:hist,darkThreshold,brightThreshold};
  }
  root.PhotoMetrics={measure};
  if(typeof module!=='undefined')module.exports={measure};
})(typeof window==='undefined'?globalThis:window);
