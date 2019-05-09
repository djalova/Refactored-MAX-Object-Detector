'use strict';

const tf = require('@tensorflow/tfjs');
const fs = require('fs');
const {Image, createCanvas} = require('canvas');


class PrePost {

    preprocess(request) {
        throw {name: "NotImplementedError", message: "This function needs to be implemented."};
    }

    postprocess(request) {
        throw {name: "NotImplementedError", message: "This function needs to be implemented."}
    }

    errorPostProcess(request, errorMessage) {
        throw {name: "NotImplementedError", message: "This function needs to be implemented."}
    }
}

class ObjectDetectorHandler extends PrePost {

    preprocess(request) {
    
        request.processedInputs['image'] = request.rawInputs['image'].map(element => {
            let base64Encoded = Buffer.from(element).toString('base64');
            const img = new Image();
            /** 
             * Note: Setting image src via data url, to avoid waiting for image to load
             *  See https://developer.mozilla.org/en-US/docs/Web/API/Canvas_API/Tutorial/Using_images#Embedding_an_image_via_data_URL
             */
            img.src = `data:image/jpeg;base64,${base64Encoded}`;
            const canvas = createCanvas(img.width, img.height);
            const ctx = canvas.getContext('2d');
            ctx.drawImage(img, 0, 0);
            const inputTensor = tf.browser.fromPixels(canvas);
            return inputTensor;
            // let base64Encoded = Buffer.from(element).toString('base64');
            // let imgBinary = new Buffer(base64Encoded, 'base64');
            // console.log(imgBinary)
            // return imgBinary;
        });
    }

    postprocess(request) {
        let categories = JSON.parse(fs.readFileSync("test/labels.json"));
        // console.log(categories)

        const threshold = request.rawInputs['threshold'];
        let predictions = [];
        let detectionScores = request.rawOutputs["detectionScores"][0];
        let detectionBoxes = request.rawOutputs["detectionBoxes"][0];
        let numDetections = request.rawOutputs["numDetections"][0];
        let detectionClasses = request.rawOutputs["detectionClasses"][0];

        for (let i = 0; i < numDetections; i++) {
            let probability = detectionScores[0, i];
            if (probability >= threshold) {
                let classesValue = detectionClasses[0, i];
                predictions.push({
                    label: categories[classesValue].class,
                    probability: probability,
                    detectionBox: detectionBoxes[0, i]
                })
            }
        }
        request.processedOutputs['status'] = "ok";
        request.processedOutputs['predictions'] = predictions;
    }
}

module.exports = {PrePost, ObjectDetectorHandler};