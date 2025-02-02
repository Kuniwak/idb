/**
 * Copyright (c) Facebook, Inc. and its affiliates.
 *
 * This source code is licensed under the MIT license found in the
 * LICENSE file in the root directory of this source tree.
 */

#import <Foundation/Foundation.h>
#import <FBControlCore/FBControlCore.h>

NS_ASSUME_NONNULL_BEGIN

@class FBIDBCommandExecutor;
@class FBIDBLogger;
@class FBIDBPortsConfiguration;
@class FBTemporaryDirectory;

@protocol FBEventReporter;

/**
 The abstract interface for a server.
 */
@protocol FBIDBCompanionServer <NSObject, FBJSONSerializable, FBiOSTargetContinuation>

/**
 The designated initializers

 @param ports the ports to use.
 @param logger the logger to use.
 @return an instance of the server.
 */
+ (instancetype)serverWithPorts:(FBIDBPortsConfiguration *)ports target:(id<FBiOSTarget>)target commandExecutor:(FBIDBCommandExecutor *)commandExecutor eventReporter:(id<FBEventReporter>)eventReporter logger:(FBIDBLogger *)logger;

/**
 Starts the server.
 */
- (FBFuture<id<FBIDBCompanionServer>> *)start;

@end

/**
 The IDB Companion.
 */
@interface FBIDBCompanionServer : NSObject <FBIDBCompanionServer>

#pragma mark Initializers

/**
 The Designated Initializer

 @param target the target to serve up
 @param temporaryDirectory the temporaryDirectory to use.
 @param ports the ports to use.
 @param eventReporter the event reporter to report to.
 @param logger the logger to us.
 @param error an error out for any error that occurs in initialization
 @return a server on success, nil otherwise.
 */
+ (nullable instancetype)companionForTarget:(id<FBiOSTarget>)target temporaryDirectory:(FBTemporaryDirectory *)temporaryDirectory ports:(FBIDBPortsConfiguration *)ports eventReporter:(id<FBEventReporter>)eventReporter logger:(id<FBControlCoreLogger>)logger error:(NSError **)error;

@end

NS_ASSUME_NONNULL_END
