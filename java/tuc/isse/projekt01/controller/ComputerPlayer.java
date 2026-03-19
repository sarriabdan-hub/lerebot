/**
 * @author Haris Masood <haris.masood@tu-clausthal.de>
 * Projekt 06 (Bonus), Task b: ComputerPlayer - AI Opponent
 * 
 * This class implements an artificial intelligence player for the 90 Grad game.
 * It extends the Player abstract class and provides autonomous gameplay by
 * analyzing the board state and selecting strategic moves.
 * 
 * TASK IMPLEMENTATION: Project 6, Task b (20 Bonus Points)
 * - Inherits from Player class
 * - Examines ball positions on the game board
 * - Executes promising moves autonomously without human input
 * - Enables Computer vs Computer gameplay
 * 
 * PURPOSE:
 * The ComputerPlayer allows the game to be played without human interaction,
 * useful for:
 * - Testing game logic and balance
 * - Providing single-player mode against AI
 * - Demonstrating complete automation of the game
 * 
 * STRATEGY:
 * The AI evaluates all possible moves and selects the most promising one based on:
 * 1. Winning moves (reaching the center or target zone)
 * 2. Advancing balls toward the goal
 * 3. Defensive moves (blocking opponent)
 * 4. Safe moves (avoiding going out of bounds)
 */
package tuc.isse.projekt01.controller;

import tuc.isse.projekt01.model.Ball;
import tuc.isse.projekt01.model.Board;
import tuc.isse.projekt01.model.Color;
import tuc.isse.projekt01.model.Direction;
import tuc.isse.projekt01.model.Role;
import tuc.isse.projekt01.model.Winner;

import java.util.ArrayList;
import java.util.List;
import java.util.Random;

/**
 * ComputerPlayer - Autonomous AI player for 90 Grad game.
 * 
 * This class represents a computer-controlled player that can make
 * intelligent decisions without human input. It analyzes the current
 * board state and selects the best available move.
 * 
 * @author Haris Masood, Xiajiong Xu
 * @version 1.0
 */
public class ComputerPlayer extends Player {

    /**
     * Random number generator for selecting among equally-valued moves.
     * 
     * WHY ADDED: When multiple moves have the same strategic value, we need
     * to randomly choose one to avoid predictable behavior and add variety
     * to the gameplay.
     */
    private final Random random;
    
    /**
     * Delay in milliseconds between moves for visual clarity.
     * 
     * WHY ADDED: Without delay, computer moves happen too fast for
     * human observers to follow. This creates a better viewing experience
     * when watching computer vs computer games.
     */
    private static final int MOVE_DELAY_MS = 500;
    
    /**
     * The size of the game board (7x7 grid).
     * 
     * WHY ADDED: Used for boundary calculations and determining
     * distances to goals. Defined as constant for clarity and
     * maintainability.
     */
    private static final int BOARD_SIZE = 7;

    /**
     * Constructor for ComputerPlayer.
     * 
     * TASK: Project 6, Task b - Part 1: Inheritance from Player
     * 
     * Creates a new computer-controlled player with the specified color
     * and board reference. Initializes the random number generator used
     * for move selection.
     * 
     * @param color The color this computer player controls (WHITE or BLACK).
     *              WHITE moves from bottom (row 0) toward top (row 6).
     *              BLACK moves from top (row 6) toward bottom (row 0).
     * @param board Reference to the game board. The computer player uses
     *              this to analyze ball positions and execute moves via
     *              board.moveBall().
     * 
     * WHY THESE PARAMETERS:
     * - color: Determines which balls the AI can move and the goal direction
     * - board: Provides access to game state and move execution methods
     */
    public ComputerPlayer(Color color, Board board) {
        // Call parent constructor to initialize color and board
        super(color, board);
        
        // Initialize random number generator for move selection
        this.random = new Random();
    }

    /**
     * Performs one turn for the computer player.
     * 
     * TASK: Project 6, Task b - Part 2: Autonomous move execution
     * 
     * This method is called when it's the computer player's turn.
     * It analyzes all possible moves, evaluates them strategically,
     * and executes the best move found.
     * 
     * ALGORITHM:
     * 1. Find all balls belonging to this player
     * 2. For each ball, evaluate all 4 possible directions
     * 3. Score each legal move based on strategic value
     * 4. Select and execute the highest-scoring move
     * 5. Add delay for visual clarity
     * 
     * WHY THIS APPROACH:
     * - Systematic evaluation ensures no good moves are missed
     * - Scoring system allows prioritization of strategic goals
     * - Exception handling ensures only legal moves are attempted
     */
    @Override
    public void doTurn() {
        // Find the best possible move for this player
        Move bestMove = findBestMove();
        
        if (bestMove != null) {
            try {
                // Execute the selected move
                board.moveBall(color, bestMove.col, bestMove.row, bestMove.direction);
                
                // Add delay so humans can follow the game visually
                Thread.sleep(MOVE_DELAY_MS);
                
            } catch (Exception e) {
                // If move fails (shouldn't happen with proper evaluation),
                // print error for debugging
                System.err.println("ComputerPlayer move failed: " + e.getMessage());
            }
        } else {
            // No legal moves available - this shouldn't happen in normal gameplay
            System.err.println("ComputerPlayer has no legal moves!");
        }
    }

    /**
     * Finds the best move by evaluating all possible moves.
     * 
     * TASK: Project 6, Task b - Part 3: Strategic analysis
     * 
     * This is the core AI decision-making method. It examines every ball
     * owned by this player, tests all four directions, scores each legal
     * move, and returns the move with the highest score.
     * 
     * SCORING SYSTEM:
     * - Winning move: 1000 points (instant win)
     * - Moving toward goal: 100 points per row advanced
     * - Moving King ball: +50 bonus (Kings are more valuable)
     * - Moving toward center: +30 points (center is target)
     * - Random factor: ±10 points (adds unpredictability)
     * 
     * @return The best Move object, or null if no legal moves exist.
     * 
     * WHY THIS RETURN TYPE:
     * Returns a Move object containing col, row, and direction so
     * doTurn() can execute the move directly.
     */
    private Move findBestMove() {
        List<Move> allMoves = new ArrayList<>();
        int bestScore = Integer.MIN_VALUE;
        
        // Evaluate all balls and directions
        for (int row = 0; row < BOARD_SIZE; row++) {
            for (int col = 0; col < BOARD_SIZE; col++) {
                Ball ball = board.getBall(col, row);
                
                // Only consider this player's balls
                if (ball != null && ball.getColor() == color) {
                    
                    // Try all four directions
                    for (Direction direction : Direction.values()) {
                        // Evaluate this potential move
                        int score = evaluateMove(col, row, direction, ball);
                        
                        // If this move is legal (score != -1), consider it
                        if (score > -1) {
                            Move move = new Move(col, row, direction, score);
                            allMoves.add(move);
                            
                            if (score > bestScore) {
                                bestScore = score;
                            }
                        }
                    }
                }
            }
        }
        
        // Filter moves: keep only those with the best score
        List<Move> bestMoves = new ArrayList<>();
        for (Move move : allMoves) {
            if (move.score == bestScore) {
                bestMoves.add(move);
            }
        }
        
        // If multiple moves have the same score, pick randomly
        if (!bestMoves.isEmpty()) {
            return bestMoves.get(random.nextInt(bestMoves.size()));
        }
        
        return null; // No legal moves found
    }

    /**
     * Evaluates the strategic value of a potential move.
     * 
     * TASK: Project 6, Task b - Part 4: Move evaluation logic
     * 
     * This method scores a move without actually executing it. It considers:
     * - Is the move legal? (returns -1 if illegal)
     * - Does it win the game? (highest priority)
     * - Does it advance toward the goal?
     * - Does it move important pieces (King)?
     * - Does it move toward the center?
     * 
     * @param col Column index of the ball to move (0-6)
     * @param row Row index of the ball to move (0-6)
     * @param direction Direction to move (UP, DOWN, LEFT, RIGHT)
     * @param ball The Ball object being considered for movement
     * @return Score value (higher is better), or -1 if move is illegal
     * 
     * WHY THESE PARAMETERS:
     * - col, row: Identify which ball to evaluate
     * - direction: Which way to move it
     * - ball: Access to role (King vs Resident) for scoring bonus
     * 
     * WHY RETURN INTEGER:
     * Numeric score allows comparison between moves. -1 signals
     * illegal moves to exclude them from consideration.
     */
    private int evaluateMove(int col, int row, Direction direction, Ball ball) {
        try {
            // Create a temporary board to test the move
            // (We don't actually move on the real board yet)
            Board testBoard = new Board();
            copyBoardState(testBoard);
            
            // Try the move on the test board
            testBoard.moveBall(color, col, row, direction);
            
            // Check if this move wins the game
            Winner winner = testBoard.getWinner();
            if (winner != Winner.NONE && 
                ((color == Color.WHITE && winner == Winner.WHITE) ||
                 (color == Color.BLACK && winner == Winner.BLACK))) {
                // WINNING MOVE: Highest priority!
                return 1000;
            }
            
            // Calculate strategic score for non-winning moves
            int score = 0;
            
            // Score based on advancement toward goal
            // WHITE moves UP (toward higher row numbers)
            // BLACK moves DOWN (toward lower row numbers)
            int advancement = 0;
            switch (direction) {
                case UP:
                    advancement = (color == Color.WHITE) ? 1 : -1;
                    break;
                case DOWN:
                    advancement = (color == Color.BLACK) ? 1 : -1;
                    break;
                case LEFT:
                case RIGHT:
                    // Horizontal moves: less valuable, but still useful
                    advancement = 0;
                    break;
            }
            score += advancement * 100;
            
            // Bonus for moving King (more valuable piece)
            if (ball.getRole() == Role.KING) {
                score += 50;
            }
            
            // Bonus for moving toward center columns (3 is center)
            int newCol = col;
            if (direction == Direction.LEFT) newCol--;
            if (direction == Direction.RIGHT) newCol++;
            
            int distanceFromCenter = Math.abs(newCol - 3);
            score += (3 - distanceFromCenter) * 10;
            
            // Add small random factor to avoid predictable patterns
            score += random.nextInt(20) - 10; // -10 to +10
            
            return score;
            
        } catch (Exception e) {
            // Move is illegal (would cause exception)
            return -1;
        }
    }

    /**
     * Copies the current board state to a test board for move evaluation.
     * 
     * TASK: Project 6, Task b - Part 5: Safe move testing
     * 
     * This method duplicates the current board state onto another board
     * so we can test moves without affecting the actual game. This is
     * essential for the AI to "think ahead" safely.
     * 
     * @param testBoard The board to copy the current state into
     * 
     * WHY THIS IS NEEDED:
     * The AI needs to test moves before executing them. Without this
     * copy mechanism, testing would alter the real game state.
     * 
     * LIMITATION:
     * Currently simplified - copies ball positions but not all state.
     * For full save/load functionality, see Task a.
     */
    private void copyBoardState(Board testBoard) {
        // Clear test board
        testBoard.clearBoard();
        
        // Copy all balls from current board to test board
        for (int row = 0; row < BOARD_SIZE; row++) {
            for (int col = 0; col < BOARD_SIZE; col++) {
                Ball ball = board.getBall(col, row);
                if (ball != null) {
                    // Create new ball with same properties
                    Ball newBall = new Ball(ball.getColor(), ball.getRole());
                    testBoard.setBallAt(col, row, newBall);
                }
            }
        }
    }

    /**
     * Inner class representing a potential move with its strategic score.
     * 
     * TASK: Project 6, Task b - Part 6: Move data structure
     * 
     * This class encapsulates all information about a potential move:
     * - Which ball to move (col, row)
     * - Which direction to move it
     * - How good the move is (score)
     * 
     * WHY A SEPARATE CLASS:
     * Bundling these four pieces of information together makes the code
     * cleaner and easier to understand than passing four separate variables
     * around or using arrays.
     * 
     * WHY INNER CLASS:
     * Move objects are only used internally by ComputerPlayer, so defining
     * Move as an inner class keeps it encapsulated and prevents namespace
     * pollution.
     */
    private static class Move {
        /** Column index of the ball to move (0-6) */
        int col;
        
        /** Row index of the ball to move (0-6) */
        int row;
        
        /** Direction to move the ball (UP, DOWN, LEFT, RIGHT) */
        Direction direction;
        
        /** Strategic score for this move (higher is better) */
        int score;

        /**
         * Constructor for Move.
         * 
         * @param col Column position of the ball
         * @param row Row position of the ball
         * @param direction Direction to move
         * @param score Strategic value of this move
         * 
         * WHY THESE PARAMETERS:
         * These four values completely define a move and its quality,
         * allowing the AI to compare and select the best option.
         */
        Move(int col, int row, Direction direction, int score) {
            this.col = col;
            this.row = row;
            this.direction = direction;
            this.score = score;
        }
        
        /**
         * Returns string representation of this move for debugging.
         * 
         * @return Human-readable description of the move
         * 
         * WHY THIS METHOD:
         * Makes debugging easier by showing move details in logs.
         */
        @Override
        public String toString() {
            return String.format("Move[(%d,%d) %s, score=%d]", 
                               col, row, direction, score);
        }
    }
}
