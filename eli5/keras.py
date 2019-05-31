# -*- coding: utf-8 -*-
"""Keras neural network explanations"""

import numpy as np
import keras
import keras.backend as K
from keras.preprocessing import image
from keras.models import Model
from keras.layers.core import Lambda

from eli5.base import Explanation
from eli5.explain import explain_prediction


# note that Sequential subclasses Model, so we can just register the Model type
# Model subclasses Network, but is using Network with this function valid?
@explain_prediction.register(Model) 
def explain_prediction_keras(estimator, doc, # model, image
                             top=None, # NOT SUPPORTED
                             top_targets=None, # NOT SUPPORTED
                             target_names=None, # rename / provide prediction labels
                             targets=None, # prediction(s) to focus on, if None take top prediction
                             feature_names=None, # NOT SUPPORTED
                             feature_re=None, # NOT SUPPORTED
                             feature_filter=None, # NOT SUPPORTED
                             # new parameters:
                             layer=None, # which layer to focus on, 
                             prediction_decoder=None, # target prediction decoding function
                            ):
    """Explain prediction of a Keras model
    doc : image, 
        must be an input acceptable by the estimator,
        (see other functions for loading/preprocessing).
    targets: predictions
        a list of predictions
        integer for ImageNet classification
    layer: valid target layer in the model to Grad-CAM on,
        one of: a valid keras layer name (str) or index (int), 
        a callable function that returns True when the desired layer is matched for the model
        if None, automatically use a helper callable function to get the last suitable Conv layer
    """
    explanation = Explanation(
        repr(estimator), # might want to replace this with something else, eg: estimator.summary()
        description='',
        error='',
        method='gradcam',
        is_regression=False, # classification vs regression model
        highlight_spaces=None, # might be relevant later when explaining text models
    )
    # TODO: grad-cam on multiple layers by passing a list of layers
    if layer is None:
        # Automatically get the layer if not provided
        # this might not be a good idea from transparency / user point of view
        layer = get_last_activation_maps
    target_layer = get_target_layer(estimator, layer)

    # get prediction to focus on
    if targets is None:
        predicted = get_target_prediction(estimator, doc, decoder=prediction_decoder)
    else:
        predicted = targets[0] 
        # TODO: take in a single target as well, not just a list
        # does it make sense to take a list of targets. You can only Grad-CAM a single target?
        # TODO: consider changing signature / types for explain_prediction generic function
        # TODO: need to find a way to show the label for the passed prediction as well as its probability
    
    heatmap = grad_cam(estimator, doc, predicted, target_layer)
    # consider renaming 'heatmap' to 'visualization'/'activations' (the output is not yet a heat map)
    heatmap = image.array_to_img(heatmap)
    original = image.array_to_img(doc[0])
    explanation.heatmap = heatmap
    explanation.image = original
    return explanation


# TODO: this will need to move to ipython.py
def show_prediction():
    raise NotImplementedError


def load_image(img, estimator=None):
    """
    Returns a single image as an array for an estimator's input
    img: one of: path to a single image file, PIL Image object, numpy array
    estimator: model instance, for resizing the image to the required input dimensions
    """
    # TODO: Take in PIL image object, or an array can also be multiple images.
    # "pipeline": path str -> PIL image -> numpy array
    xDims = None
    if estimator is not None:
        xDims = estimator.input_shape[1:3]
    im = image.load_img(img, target_size=xDims)
    x = image.img_to_array(im)

    # we need to insert an axis at the 0th position to indicate the batch size
    # this is required by the keras predict() function
    x = np.expand_dims(x, axis=0)
    return x


def applications_preprocessing(x, estimator):
    """
    x: image array,
    estimator: estimator instance.
    """
    # Apply preprocess_input function in keras.applications for appropriate model
    try:
        f = getattr(keras.applications, estimator.name.lower()).preprocess_input
    except AttributeError:
        raise AttributeError('Could not get the preprocessing function')
    else:
        x = f(x)
        return x


def get_target_prediction(model, x, decoder=None):
    predictions = model.predict(x)
    if decoder is not None:
        # TODO: check if decoder is callable?
        # FIXME: it is not certain that we need such indexing into the decoder's output
        top_1 = decoder(predictions)[0][0] 
        ncode, label, proba = top_1
        # TODO: do I print, log, or append to 'description' this output?
        print('Predicted class:') 
        print('%s (%s) with probability %.2f' % (label, ncode, proba))
    # FIXME: non-classification tasks
    predicted_class = np.argmax(predictions)
    return predicted_class


def get_target_layer(estimator, desired_layer):
    """
    Return instance of the desired layer in the model.
    estimator: model whose layer is to be gotten
    desired_layer: one of: integer index, string name of the layer, 
    callable that returns True if a layer instance matches.
    """
    if isinstance(desired_layer, int):
        # conv_output =  [l for l in model.layers if l.name is layer_name]
        # conv_output = conv_output[0]
        # bottom-up horizontal graph traversal
        target_layer = estimator.get_layer(index=desired_layer)
        # These can raise ValueError if the layer index / name specified is not found
    elif isinstance(desired_layer, str):
        target_layer = estimator.get_layer(name=desired_layer)
    elif callable(desired_layer):
        # is 'callable()' the right check to use here?
        l = estimator.get_layer(index=-4)
        # FIXME: don't hardcode four
        # actually iterate through the list of layers backwards (using negative indexing with get_layer()) until find the desired layer
        target_layer = l if desired_layer(l) else None
        if target_layer is None:
            # If can't find, raise error
            raise ValueError('Target layer could not be found using callable %s' % desired_layer)
    else:
        raise ValueError('Invalid desired_layer (must be str, int, or callable): "%s"' % desired_layer)

    # TODO: check target_layer dimensions (is it possible to perform Grad-CAM on it?)
    return target_layer


def get_last_activation_maps(estimator):
    # TODO: automatically get last Conv layer if layer_name and layer_index are None
    # Some ideas:
    # 1. look at layer name, exclude things like "softmax", "global average pooling", 
    # etc, include things like "conv" (but watch for false positives)
    # 2. look at layer input/output dimensions, to ensure they match
    return True


def explain_images():
    # Take a directory of images and call explain_prediction_keras on each image
    raise NotImplementedError

def explain_layers():
    # Take a list of layers and call explain_prediction_keras on each layer
    raise NotImplementedError


def target_category_loss(x, category_index, nb_classes):
    # return tf.multiply(x, K.one_hot([category_index], nb_classes))
    return x * K.one_hot([category_index], nb_classes)


def target_category_loss_output_shape(input_shape):
    return input_shape


def normalize(x):
    # L2 norm
    return x / (K.sqrt(K.mean(K.square(x))) + 1e-5)


def compute_gradients(tensor, var_list):
    # grads = tf.gradients(tensor, var_list)
    # return [grad if grad is not None else tf.zeros_like(var) for var, grad in zip(var_list, grads)]
    grads = K.gradients(tensor, var_list)
    return [grad if grad is not None else K.zeros_like(var) for var, grad in zip(var_list, grads)]


def gap(tensor): # FIXME: might want to rename this argument
    """Global Average Pooling"""
    # First two axes only
    return np.mean(tensor, axis=(0, 1))


def relu(tensor):
    """ReLU"""
    return np.maximum(tensor, 0)


def get_localization_map(activation_maps, weights): # consider renaming this function to 'weighted_lincomb'
    localization_map = np.ones(activation_maps.shape[0:2], dtype=np.float32)
    for i, w in enumerate(weights):
        localization_map += w * activation_maps[:,:,i] # weighted linear combination
    return localization_map


def grad_cam(estimator, image, prediction_index, layer):
    # FIXME: this assumes that we are doing classification
    # also we make the explicit assumption that we are dealing with images

    # nb_classes = 1000 # FIXME: number of classes can be variable
    nb_classes = estimator.output_shape[1] # TODO: test this

    # FIXME: rename these "layer" variables
    target_layer = lambda x: target_category_loss(x, prediction_index, nb_classes)
    x = Lambda(target_layer, output_shape = target_category_loss_output_shape)(estimator.output)
    model = Model(inputs=estimator.input, outputs=x)
    loss = K.sum(model.output)

    # we need to access the output attribute, else we get a TypeError: Failed to convert object to tensor
    conv_output = layer.output

    grads = normalize(compute_gradients(loss, [conv_output])[0])
    gradient_function = K.function([model.input], [conv_output, grads])

    output, grads_val = gradient_function([image]) # work happens here
    output, grads_val = output[0,:], grads_val[0,:,:,:] # FIXME: this probably assumes that the layer is a width*height filter

    weights = gap(grads_val)

    lmap = get_localization_map(output, weights)
    lmap = relu(lmap)

    lmap = lmap / np.max(lmap) # probability
    lmap = 255*lmap # 0...255 float
    # we need to insert a "channels" axis to have an image (channels last by default)
    lmap = np.expand_dims(lmap, axis=-1)

    return lmap


#
# Credits:
# Jacob Gildenblat for "https://github.com/jacobgil/keras-grad-cam",
# author of "https://github.com/PowerOfCreation/keras-grad-cam" for various fixes.
#